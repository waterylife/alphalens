"""Portfolio API: read-only views over the local SQLite store."""

from __future__ import annotations

from collections import defaultdict
import secrets
import time

from fastapi import APIRouter, File, Form, Header, HTTPException, UploadFile

from backend.portfolio import db, service, tags as tags_cfg
from backend.portfolio.schemas import (
    AllocationBucket,
    FxSnapshot,
    Holding,
    HoldingTagPatch,
    ImportRequest,
    ImportResult,
    RefreshPricesResult,
    ScreenshotParseResult,
    ScreenshotRow,
    Summary,
    SyncResult,
    SyncRun,
    TagsConfig,
    TiantianBrowserImportRequest,
)
from backend.portfolio.sources import screenshot as ss


router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])

_IMPORT_TOKENS: dict[str, float] = {}
_TOKEN_TTL_SECONDS = 15 * 60


def _cleanup_tokens() -> None:
    now = time.time()
    expired = [token for token, until in _IMPORT_TOKENS.items() if until < now]
    for token in expired:
        _IMPORT_TOKENS.pop(token, None)


def _consume_token(token: str | None) -> None:
    _cleanup_tokens()
    if not token or token not in _IMPORT_TOKENS:
        raise HTTPException(status_code=403, detail="导入 token 无效或已过期")
    _IMPORT_TOKENS.pop(token, None)


@router.get("/holdings", response_model=list[Holding])
def list_holdings() -> list[Holding]:
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT * FROM holdings ORDER BY market_value_cny DESC"
        ).fetchall()
        total_mv = conn.execute(
            "SELECT COALESCE(SUM(market_value_cny), 0) FROM holdings"
        ).fetchone()[0] or 0.0

    out: list[Holding] = []
    for r in rows:
        weight = (r["market_value_cny"] / total_mv) if total_mv else 0.0
        out.append(Holding(
            id=r["id"],
            market=r["market"],
            asset_class=r["asset_class"],
            tag_l1=r["tag_l1"],
            tag_l2=r["tag_l2"],
            name=r["name"],
            code=r["code"],
            currency=r["currency"],
            current_price=r["current_price"],
            cost_price=r["cost_price"],
            quantity=r["quantity"],
            cost_value_cny=r["cost_value_cny"],
            market_value_cny=r["market_value_cny"],
            unrealized_pnl_cny=r["unrealized_pnl_cny"],
            return_pct=r["return_pct"],
            broker=r["broker"],
            weight=round(weight, 6),
            as_of=r["as_of"],
        ))
    return out


@router.get("/summary", response_model=Summary)
def get_summary() -> Summary:
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT market, asset_class, tag_l1, broker, "
            "       cost_value_cny, market_value_cny, unrealized_pnl_cny, as_of "
            "FROM holdings"
        ).fetchall()
        fx_rows = conn.execute(
            "SELECT pair, rate, as_of FROM fx_rates ORDER BY as_of DESC"
        ).fetchall()
        last_run = conn.execute(
            "SELECT MAX(finished_at) FROM sync_runs WHERE status='ok'"
        ).fetchone()[0]

    total_mv = sum(r["market_value_cny"] for r in rows)
    total_cv = sum(r["cost_value_cny"] for r in rows)
    total_pnl = sum((r["unrealized_pnl_cny"] or 0.0) for r in rows)
    return_pct = ((total_mv / total_cv - 1) * 100) if total_cv else None

    def bucket(field: str) -> list[AllocationBucket]:
        agg: dict[str, float] = defaultdict(float)
        for r in rows:
            key = r[field] or "未分类"
            agg[key] += r["market_value_cny"]
        items = sorted(agg.items(), key=lambda kv: kv[1], reverse=True)
        return [
            AllocationBucket(
                key=k,
                market_value_cny=round(v, 2),
                weight=round(v / total_mv, 6) if total_mv else 0.0,
            )
            for k, v in items
        ]

    # Dedupe FX pairs to most-recent rate per pair
    fx_seen: dict[str, FxSnapshot] = {}
    for r in fx_rows:
        if r["pair"] not in fx_seen:
            fx_seen[r["pair"]] = FxSnapshot(
                pair=r["pair"], rate=r["rate"], as_of=r["as_of"]
            )

    return Summary(
        total_market_value_cny=round(total_mv, 2),
        total_cost_value_cny=round(total_cv, 2),
        total_unrealized_pnl_cny=round(total_pnl, 2),
        total_return_pct=round(return_pct, 2) if return_pct is not None else None,
        n_positions=len(rows),
        last_updated=last_run,
        fx_rates=list(fx_seen.values()),
        by_market=bucket("market"),
        by_asset_class=bucket("asset_class"),
        by_tag_l1=bucket("tag_l1"),
        by_broker=bucket("broker"),
    )


@router.post("/sync/futu", response_model=SyncResult)
def sync_futu() -> SyncResult:
    try:
        result = service.sync_futu()
    except ConnectionError as e:
        raise HTTPException(status_code=503, detail=f"Futu OpenD 连接失败：{e}")
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"同步失败：{e}")
    return SyncResult(**result)


@router.post("/refresh-prices", response_model=RefreshPricesResult)
def refresh_prices(force: bool = False) -> RefreshPricesResult:
    """Refresh prices using cached quotes within the TTL window
    (PORTFOLIO_QUOTES_TTL, default 30 min). Pass ?force=true to ignore
    the cache and re-hit upstream APIs."""
    try:
        result = service.refresh_prices(force=force)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"刷新价格失败：{e}")
    return RefreshPricesResult(**result)


@router.get("/sync-runs", response_model=list[SyncRun])
def list_sync_runs(limit: int = 20) -> list[SyncRun]:
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT id, source, started_at, finished_at, status, n_rows, error_msg "
            "FROM sync_runs ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [SyncRun(**dict(r)) for r in rows]


_VALID_BROKERS = {"tiantian", "eastmoney", "ant"}


@router.post("/screenshot-parse", response_model=ScreenshotParseResult)
async def parse_screenshot(
    image: UploadFile = File(...),
    broker: str = Form(...),
) -> ScreenshotParseResult:
    if broker not in _VALID_BROKERS:
        raise HTTPException(
            status_code=400,
            detail=f"broker 必须是 {sorted(_VALID_BROKERS)} 之一,收到 {broker}",
        )

    image_bytes = await image.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="未收到图片数据")

    mime = image.content_type or "image/png"

    try:
        parser = ss.get_parser()
        parsed = parser.parse(image_bytes, broker=broker, mime=mime)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"解析失败: {e}")

    return ScreenshotParseResult(
        rows=[ScreenshotRow(**vars(r)) for r in parsed.rows],
        warnings=parsed.warnings,
    )


@router.get("/tags", response_model=TagsConfig)
def get_tags() -> TagsConfig:
    return TagsConfig(**tags_cfg.load_tags())


@router.patch("/holdings/{holding_id}", response_model=Holding)
def patch_holding_tags(holding_id: int, patch: HoldingTagPatch) -> Holding:
    """Update tag_l1 / tag_l2 on one row. Empty string -> NULL."""
    fields = patch.model_dump(exclude_unset=True)
    if not fields:
        raise HTTPException(status_code=400, detail="未提供任何字段")

    sets, params = [], []
    for k, v in fields.items():
        sets.append(f"{k}=?")
        params.append(v if v else None)
    params.append(holding_id)

    with db.connect() as conn:
        cur = conn.execute(
            f"UPDATE holdings SET {', '.join(sets)} WHERE id=?", params
        )
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail=f"holding {holding_id} 不存在")
        row = conn.execute("SELECT * FROM holdings WHERE id=?", (holding_id,)).fetchone()
        total_mv = conn.execute(
            "SELECT COALESCE(SUM(market_value_cny), 0) FROM holdings"
        ).fetchone()[0] or 0.0

    weight = (row["market_value_cny"] / total_mv) if total_mv else 0.0
    return Holding(
        id=row["id"], market=row["market"], asset_class=row["asset_class"],
        tag_l1=row["tag_l1"], tag_l2=row["tag_l2"], name=row["name"], code=row["code"],
        currency=row["currency"], current_price=row["current_price"],
        cost_price=row["cost_price"], quantity=row["quantity"],
        cost_value_cny=row["cost_value_cny"], market_value_cny=row["market_value_cny"],
        unrealized_pnl_cny=row["unrealized_pnl_cny"], return_pct=row["return_pct"],
        broker=row["broker"], weight=round(weight, 6), as_of=row["as_of"],
    )


@router.post("/import-rows", response_model=ImportResult)
def import_rows(req: ImportRequest) -> ImportResult:
    if not req.rows:
        raise HTTPException(status_code=400, detail="rows 为空,无可导入数据")
    try:
        result = service.import_rows(req.broker, [r.model_dump() for r in req.rows])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"导入失败: {e}")
    return ImportResult(**result)


@router.post("/tiantian-browser-token")
def create_tiantian_browser_token() -> dict:
    """Create a short-lived token embedded into the one-time browser collector."""
    _cleanup_tokens()
    token = secrets.token_urlsafe(24)
    expires_at = time.time() + _TOKEN_TTL_SECONDS
    _IMPORT_TOKENS[token] = expires_at
    return {"token": token, "expires_in_seconds": _TOKEN_TTL_SECONDS}


@router.post("/tiantian-browser-import", response_model=ImportResult)
def import_tiantian_browser_rows(
    req: TiantianBrowserImportRequest,
    x_alphalens_import_token: str | None = Header(default=None),
) -> ImportResult:
    _consume_token(x_alphalens_import_token)
    if not req.rows:
        raise HTTPException(status_code=400, detail="rows 为空,无可导入数据")
    try:
        result = service.import_tiantian_browser_rows([r.model_dump() for r in req.rows])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"天天基金页面导入失败: {e}")
    return ImportResult(**result)
