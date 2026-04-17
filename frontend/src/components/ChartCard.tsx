import { ReactNode } from "react";

interface Props {
  title: string;
  description?: string;
  children: ReactNode;
  action?: ReactNode;
}

export function ChartCard({ title, description, children, action }: Props) {
  return (
    <div className="bg-white border border-slate-200 rounded-xl shadow-sm">
      <div className="flex items-start justify-between px-5 pt-5">
        <div>
          <h3 className="text-base font-semibold text-slate-900">{title}</h3>
          {description && (
            <p className="text-xs text-slate-500 mt-0.5">{description}</p>
          )}
        </div>
        {action}
      </div>
      <div className="p-3">{children}</div>
    </div>
  );
}
