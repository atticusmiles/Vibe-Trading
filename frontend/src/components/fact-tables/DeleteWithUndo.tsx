import { useState } from "react";
import { toast } from "sonner";

export function useDeleteWithUndo(onDelete: () => Promise<void>, onUndo: () => Promise<void>, label = "项目") {
  const [deleting, setDeleting] = useState(false);

  const performDelete = async () => {
    setDeleting(true);
    try {
      await onDelete();
      toast.success(`${label} 已移除`, {
        action: { label: "撤销", onClick: async () => { await onUndo(); toast.success(`${label} 已恢复`); } },
        duration: 5000,
      });
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "删除失败");
    } finally {
      setDeleting(false);
    }
  };

  return { performDelete, deleting };
}
