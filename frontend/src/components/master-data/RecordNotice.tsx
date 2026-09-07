import { useState } from "react";
import { CheckCircle, X } from "@phosphor-icons/react";
import { useI18n } from "../../i18n";

type NoticeKind = "created" | "saved" | "archived";
export function useRecordNotice() {
  const { text } = useI18n();
  const [message, setMessage] = useState<{
    kind: NoticeKind;
    sequence: number;
  } | null>(null);
  const notify = (kind: NoticeKind) =>
    setMessage((previous) => ({
      kind,
      sequence: (previous?.sequence ?? 0) + 1,
    }));
  const labels: Record<NoticeKind, string> = {
    created: text("记录已创建。", "Record created."),
    saved: text("更改已保存。", "Changes saved."),
    archived: text(
      "记录已归档，历史引用仍然保留。",
      "Record archived. Historical references are preserved.",
    ),
  };
  const notice = message && (
    <div className="record-notice">
      <div key={message.sequence} role="status">
        <CheckCircle size={19} aria-hidden />
        <span>{labels[message.kind]}</span>
      </div>
      <button
        className="icon-button"
        type="button"
        aria-label={text("关闭操作提示", "Dismiss update")}
        onClick={() => setMessage(null)}
      >
        <X size={16} />
      </button>
    </div>
  );
  return { notice, notify };
}
