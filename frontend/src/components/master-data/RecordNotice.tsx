import { zhCN } from "../../locales/zh-CN/console";
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
    created: text(zhCN.componentsMasterDataRecordNotice.recordCreated, "Record created."),
    saved: text(zhCN.componentsMasterDataRecordNotice.changesSaved, "Changes saved."),
    archived: text(
      zhCN.componentsMasterDataRecordNotice.recordArchivedHistoricalReferencesArePreserved,
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
        aria-label={text(zhCN.componentsMasterDataRecordNotice.dismissUpdate, "Dismiss update")}
        onClick={() => setMessage(null)}
      >
        <X size={16} />
      </button>
    </div>
  );
  return { notice, notify };
}
