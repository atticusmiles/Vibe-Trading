import { FileText } from "lucide-react";
import type { ReactNode } from "react";

export function DetailPanel({ children, isEmpty }: { children?: ReactNode; isEmpty?: boolean }) {
  if (isEmpty) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-2 text-muted-foreground">
        <FileText className="h-8 w-8" />
        <p className="text-sm">选择一个项目查看详情</p>
      </div>
    );
  }
  return <div className="flex-1 overflow-y-auto overflow-x-hidden p-5 break-words">{children}</div>;
}
