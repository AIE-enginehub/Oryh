import { zhCN } from "../locales/zh-CN/console";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState, type FormEvent } from "react";

import {
  createApiKey,
  listApiKeys,
  listApiKeyOwners,
  updateApiKey,
  type ApiKey,
  type ApiKeyOwner,
  type CreatedApiKey,
} from "../api/configuration";
import { ConfirmDialog } from "../components/master-data/ConfirmDialog";
import { Drawer } from "../components/master-data/Drawer";
import { apiErrorMessage, ListState } from "../components/master-data/ListState";
import { Pagination } from "../components/master-data/Pagination";
import { useI18n } from "../i18n";
import "./api-keys.css";
import "./configuration.css";

const PAGE_SIZE = 20;

function keyAvailability(key: ApiKey, text: (chinese: string, english: string) => string): { className: string; label: string } {
  if (!key.is_active) return { className: "inactive", label: text(zhCN.pagesApiKeysPage.keyDisabled, "Key disabled") };
  if (key.effective_active) return { className: "active", label: text(zhCN.pagesApiKeysPage.valid, "Valid") };
  if (!key.user_id || key.user_status === "active") return { className: "blocked", label: text(zhCN.pagesApiKeysPage.currentlyUnavailable, "Currently unavailable") };
  if (key.user_status === "disabled") return { className: "blocked", label: text(zhCN.pagesApiKeysPage.userDisabled, "User disabled") };
  if (key.user_status === "invited") return { className: "blocked", label: text(zhCN.pagesApiKeysPage.userNotActivated, "User not activated") };
  return { className: "blocked", label: text(zhCN.pagesApiKeysPage.userNotFound, "User not found") };
}

export function ApiKeysPage() {
  const { language, text } = useI18n();
  const queryClient = useQueryClient();
  const [keyword, setKeyword] = useState("");
  const [keywordDraft, setKeywordDraft] = useState("");
  const [status, setStatus] = useState<"" | "active" | "inactive">("");
  const [page, setPage] = useState(1);
  const [createOpen, setCreateOpen] = useState(false);
  const [label, setLabel] = useState("default");
  const [userId, setUserId] = useState("");
  const [selectedOwner, setSelectedOwner] = useState<ApiKeyOwner | null>(null);
  const [ownerKeyword, setOwnerKeyword] = useState("");
  const [ownerKeywordDraft, setOwnerKeywordDraft] = useState("");
  const [ownerPage, setOwnerPage] = useState(1);
  const [validation, setValidation] = useState<string | null>(null);
  const [created, setCreated] = useState<CreatedApiKey | null>(null);
  const [copyState, setCopyState] = useState<"idle" | "copied" | "failed">("idle");
  const [deactivating, setDeactivating] = useState<ApiKey | null>(null);

  const keys = useQuery({
    queryKey: ["api-keys", { keyword, status, page }],
    queryFn: () => listApiKeys({ keyword: keyword || undefined, status: status || undefined, page, size: PAGE_SIZE }),
    placeholderData: keepPreviousData,
  });
  const owners = useQuery({
    queryKey: ["api-key-owners", { keyword: ownerKeyword, page: ownerPage }],
    queryFn: () => listApiKeyOwners({ keyword: ownerKeyword || undefined, page: ownerPage, size: 20 }),
    enabled: createOpen,
    retry: false,
  });

  useEffect(() => {
    const pages = keys.data?.meta.pages;
    if (pages && page > pages) setPage(pages);
  }, [keys.data?.meta.pages, page]);

  const ownerOptions = useMemo(() => {
    const values = [...(owners.data?.data ?? [])];
    if (selectedOwner && !values.some((owner) => owner.id === selectedOwner.id)) values.unshift(selectedOwner);
    return values;
  }, [owners.data?.data, selectedOwner]);

  const create = useMutation({
    mutationFn: () => createApiKey({ label: label.trim() || null, user_id: userId || null }),
    onSuccess: async (result) => {
      setCreateOpen(false);
      setCreated(result);
      setCopyState("idle");
      await queryClient.invalidateQueries({ queryKey: ["api-keys"] });
    },
  });

  const deactivate = useMutation({
    mutationFn: (key: ApiKey) => updateApiKey(key.id, { is_active: false }),
    onSuccess: async () => {
      setDeactivating(null);
      await queryClient.invalidateQueries({ queryKey: ["api-keys"] });
    },
  });

  const reactivate = useMutation({
    mutationFn: (key: ApiKey) => updateApiKey(key.id, { is_active: true }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["api-keys"] }),
  });

  const openCreate = () => {
    if (created) return;
    setLabel("default");
    setUserId("");
    setSelectedOwner(null);
    setOwnerKeyword("");
    setOwnerKeywordDraft("");
    setOwnerPage(1);
    setValidation(null);
    create.reset();
    setCreateOpen(true);
  };

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (label.trim().length > 200) {
      setValidation(text(zhCN.pagesApiKeysPage.theLabelCannotExceed200Characters, "The label cannot exceed 200 characters."));
      return;
    }
    setValidation(null);
    create.mutate();
  };

  const copySecret = async () => {
    if (!created) return;
    try {
      await navigator.clipboard.writeText(created.plain_text_api_key);
      setCopyState("copied");
    } catch {
      setCopyState("failed");
    }
  };

  const dismissCreated = () => {
    setCreated(null);
    setCopyState("idle");
    create.reset();
  };

  return (
    <div className="automation-page" data-testid="api-keys-page">
      <header className="page-intro">
        <div>
          <span className="eyebrow">{text(zhCN.pagesApiKeysPage.credentials, "Credentials")}</span>
          <h2>{text(zhCN.pagesApiKeysPage.accessCredentials, "Access credentials")}</h2>
          <p>{text(zhCN.pagesApiKeysPage.companyCredentialsRepresentTheWorkspacePersonalCredentialsActAs, "Company credentials represent the workspace; personal credentials act as that user and remain subject to the user's current role permissions.")}</p>
        </div>
        <div className="page-actions"><a className="button" href="/web/connect">{text(zhCN.pagesApiKeysPage.connectNewDevice, "Connect new device")}</a><button className="button primary" type="button" disabled={Boolean(created)} title={created ? text(zhCN.pagesApiKeysPage.saveAndCloseTheCurrentCredentialFirst, "Save and close the current credential first") : undefined} onClick={openCreate}>{text(zhCN.pagesApiKeysPage.createCredential, "Create credential")}</button></div>
      </header>

      {created && <section className="secret-card" aria-labelledby="created-key-title">
        <div><span className="eyebrow" role="status" aria-live="polite">{text(zhCN.pagesApiKeysPage.credentialCreatedShownOnlyOnce, "Credential created — shown only once")}</span><h3 id="created-key-title">{text(zhCN.pagesApiKeysPage.saveTheCredentialForNow(`${created.api_key.label || zhCN.pagesApiKeysPage.untitled}`), `Save the credential for “${created.api_key.label || "Untitled"}” now`)}</h3><p>{text(zhCN.pagesApiKeysPage.youCannotViewItAgainAfterClosingThisPanel, "You cannot view it again after closing this panel. If it is lost, disable it and create a new credential.")}</p></div>
        <code tabIndex={0} aria-label={text(zhCN.pagesApiKeysPage.newAccessCredentialCopyAndStoreItSecurelyNow, "New access credential; copy and store it securely now")}>{created.plain_text_api_key}</code>
        <div><button className="button primary" type="button" onClick={() => void copySecret()}>{copyState === "copied" ? text(zhCN.pagesApiKeysPage.copied, "Copied") : text(zhCN.pagesApiKeysPage.copyCredential, "Copy credential")}</button><button className="button quiet" type="button" onClick={dismissCreated}>{text(zhCN.pagesApiKeysPage.savedClose, "Saved — close")}</button></div>
        {copyState === "failed" && <small role="alert">{text(zhCN.pagesApiKeysPage.theBrowserDidNotAllowAutomaticCopyingSelectAnd, "The browser did not allow automatic copying. Select and copy the credential manually.")}</small>}
      </section>}

      {reactivate.isError && <div className="form-error" role="alert">{apiErrorMessage(reactivate.error)}</div>}

      <section className="data-panel" aria-label={text(zhCN.pagesApiKeysPage.accessCredentialList, "Access credential list")}>
        <header className="section-bar">
          <div><strong>{text(zhCN.pagesApiKeysPage.workspaceCredentials, "Workspace credentials")}</strong><small>{text(zhCN.pagesApiKeysPage.disablingACredentialTakesEffectImmediatelyItsValueIs, "Disabling a credential takes effect immediately; its value is never shown again in this list.")}</small></div>
          <form className="compact-filters" onSubmit={(e) => { e.preventDefault(); setKeyword(keywordDraft.trim()); setPage(1); }}>
            <input aria-label={text(zhCN.pagesApiKeysPage.searchAccessCredentials, "Search access credentials")} placeholder={text(zhCN.pagesApiKeysPage.searchLabels, "Search labels")} value={keywordDraft} onChange={(e) => setKeywordDraft(e.target.value)} />
            <select aria-label={text(zhCN.pagesApiKeysPage.credentialStatus, "Credential status")} value={status} onChange={(e) => { setStatus(e.target.value as typeof status); setPage(1); }}><option value="">{text(zhCN.pagesApiKeysPage.allStatuses, "All statuses")}</option><option value="active">{text(zhCN.pagesApiKeysPage.active, "Active")}</option><option value="inactive">{text(zhCN.pagesApiKeysPage.inactive, "Inactive")}</option></select>
            <button className="button compact" type="submit">{text(zhCN.pagesApiKeysPage.filter, "Filter")}</button>
          </form>
        </header>
        <ListState
          loading={keys.isPending}
          error={keys.isError ? apiErrorMessage(keys.error) : null}
          empty={Boolean(keys.data && keys.data.data.length === 0)}
          emptyTitle={text(zhCN.pagesApiKeysPage.noAccessCredentialsYet, "No access credentials yet")}
          emptyDescription={text(zhCN.pagesApiKeysPage.createACompanyCredentialOrAPersonalCredentialFor, "Create a company credential or a personal credential for a specific user.")}
          onRetry={() => void keys.refetch()}
        >
          {keys.data && <>
            <div className="table-scroll"><table className="data-table keys-table">
              <thead><tr><th>{text(zhCN.pagesApiKeysPage.label, "Label")}</th><th>{text(zhCN.pagesApiKeysPage.type, "Type")}</th><th>{text(zhCN.pagesApiKeysPage.identity, "Identity")}</th><th>{text(zhCN.pagesApiKeysPage.currentEffectiveRole, "Current effective role")}</th><th>{text(zhCN.pagesApiKeysPage.status, "Status")}</th><th>{text(zhCN.pagesApiKeysPage.created, "Created")}</th><th><span className="sr-only">{text(zhCN.pagesApiKeysPage.actions, "Actions")}</span></th></tr></thead>
              <tbody>{keys.data.data.map((key) => {
                const availability = keyAvailability(key, text);
                return <tr key={key.id}>
                <td><strong>{key.label || text(zhCN.pagesApiKeysPage.untitled, "Untitled")}</strong><small className="mono-cell">{key.id.slice(0, 8)}…</small></td>
                <td><span className={`key-kind ${key.user_id ? "user" : "service"}`}>{key.user_id ? text(zhCN.pagesApiKeysPage.personal, "Personal") : text(zhCN.pagesApiKeysPage.company, "Company")}</span></td>
                <td>{key.user_id ? <><strong>{key.user_name || key.user_email || text(zhCN.pagesApiKeysPage.deletedUser, "Deleted user")}</strong><small className="mono-cell">{key.user_email || `${key.user_id.slice(0, 8)}…`}</small></> : <span className="muted-value">{text(zhCN.pagesApiKeysPage.entireWorkspace, "Entire workspace")}</span>}</td>
                <td>{key.effective_role
                  ? <><strong className="mono-cell">{key.effective_role}</strong>{key.user_id && key.role !== key.effective_role && <small>{text(zhCN.pagesApiKeysPage.issuedAs, "Issued as: ")}{key.role}</small>}</>
                  : <><span className="muted-value">{text(zhCN.pagesApiKeysPage.noEffectiveRole, "No effective role")}</span><small>{text(zhCN.pagesApiKeysPage.issuedAs, "Issued as: ")}{key.role}</small></>}</td>
                <td><span className={`status-badge ${availability.className}`}>{availability.label}</span></td>
                <td>{new Intl.DateTimeFormat(language, { dateStyle: "medium" }).format(new Date(key.created_at))}</td>
                <td className="row-actions">{key.is_active
                  ? <button className="text-action danger-text" type="button" onClick={() => { deactivate.reset(); setDeactivating(key); }}>{text(zhCN.pagesApiKeysPage.inactive, "Disable")}</button>
                  : <button className="text-action" type="button" disabled={reactivate.isPending} onClick={() => reactivate.mutate(key)}>{text(zhCN.pagesApiKeysPage.reEnable, "Re-enable")}</button>}
                </td>
              </tr>})}</tbody>
            </table></div>
            <Pagination meta={keys.data.meta} onPageChange={setPage} />
          </>}
        </ListState>
      </section>

      <Drawer
        open={createOpen}
        title={text(zhCN.pagesApiKeysPage.createAccessCredential, "Create access credential")}
        description={text(zhCN.pagesApiKeysPage.theCredentialIsShownOnlyOnceAfterCreationHave, "The credential is shown only once after creation. Have a secure storage location ready.")}
        submitLabel={text(zhCN.pagesApiKeysPage.createCredential, "Create credential")}
        busy={create.isPending}
        error={validation || (create.isError ? apiErrorMessage(create.error) : null)}
        onClose={() => !create.isPending && setCreateOpen(false)}
        onSubmit={submit}
      >
        <div className="field-grid">
          <div className="field span-2"><label htmlFor="key-label">{text(zhCN.pagesApiKeysPage.label, "Label")}</label><input id="key-label" maxLength={200} value={label} onChange={(e) => setLabel(e.target.value)} /></div>
          <div className="field span-2 api-key-owner-field"><label htmlFor="key-user">{text(zhCN.pagesApiKeysPage.bindUserOptional, "Bind user (optional)")}</label>
            <div className="owner-search"><input aria-label={text(zhCN.pagesApiKeysPage.searchEligibleUsers, "Search eligible users")} placeholder={text(zhCN.pagesApiKeysPage.searchByNameOrEmail, "Search by name or email")} value={ownerKeywordDraft} onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); setOwnerKeyword(ownerKeywordDraft.trim()); setOwnerPage(1); } }} onChange={(e) => setOwnerKeywordDraft(e.target.value)} /><button className="button compact" type="button" onClick={() => { setOwnerKeyword(ownerKeywordDraft.trim()); setOwnerPage(1); }}>{text(zhCN.pagesApiKeysPage.search, "Search")}</button></div>
            <select id="key-user" value={userId} disabled={owners.isPending || owners.isError} onChange={(e) => { const id = e.target.value; setUserId(id); setSelectedOwner(ownerOptions.find((owner) => owner.id === id) ?? null); }}><option value="">{text(zhCN.pagesApiKeysPage.companyCredential, "Company credential")}</option>{ownerOptions.map((owner) => <option key={owner.id} value={owner.id}>{owner.name || owner.email} ({owner.role})</option>)}</select>
            {owners.isPending && <small>{text(zhCN.pagesApiKeysPage.loadingEligibleUsers, "Loading eligible users…")}</small>}
            {owners.isError && <small className="field-error" role="alert">{text(zhCN.pagesApiKeysPage.theUserDirectoryIsTemporarilyUnavailableRetryTheSearch, "The user directory is temporarily unavailable. Retry the search or create a company credential.")}</small>}
            {owners.data && <div className="owner-pagination"><span>{text(zhCN.pagesApiKeysPage.activeUsers(`${owners.data.meta.total}`), `${owners.data.meta.total} active users`)}</span><div><button type="button" className="text-action" disabled={ownerPage <= 1} onClick={() => setOwnerPage((current) => current - 1)}>{text(zhCN.pagesApiKeysPage.previous, "Previous")}</button><span>{owners.data.meta.page} / {owners.data.meta.pages}</span><button type="button" className="text-action" disabled={ownerPage >= owners.data.meta.pages} onClick={() => setOwnerPage((current) => current + 1)}>{text(zhCN.pagesApiKeysPage.next, "Next")}</button></div></div>}
          </div>
          <aside className="key-explanation field span-2"><strong>{userId ? text(zhCN.pagesApiKeysPage.personalAccessCredential, "Personal access credential") : text(zhCN.pagesApiKeysPage.workspaceAccessCredential, "Workspace access credential")}</strong><p>{userId ? text(zhCN.pagesApiKeysPage.everyActionIsAttributedToTheSelectedUserAnd, "Every action is attributed to the selected user and inherits that user's role permissions in real time.") : text(zhCN.pagesApiKeysPage.suitableForAutomationAgentsAndSystemConnectionsActingFor, "Suitable for automation agents and system connections acting for the whole workspace.")}</p></aside>
        </div>
      </Drawer>

      <ConfirmDialog
        open={deactivating !== null}
        title={text(zhCN.pagesApiKeysPage.disable(`${deactivating?.label || zhCN.pagesApiKeysPage.message2}`), `Disable “${deactivating?.label || "Untitled credential"}”?`)}
        description={text(zhCN.pagesApiKeysPage.agentsAndConnectionsThatDependOnThisCredentialWill, "Agents and connections that depend on this credential will immediately lose access to Oryh. An administrator can re-enable it later.")}
        kicker={text(zhCN.pagesApiKeysPage.disableCredential, "Disable credential")}
        confirmLabel={text(zhCN.pagesApiKeysPage.disableCredential2, "Disable credential")}
        busyLabel={text(zhCN.pagesApiKeysPage.disabling, "Disabling…")}
        busy={deactivate.isPending}
        error={deactivate.isError ? apiErrorMessage(deactivate.error) : null}
        onCancel={() => !deactivate.isPending && setDeactivating(null)}
        onConfirm={() => deactivating && deactivate.mutate(deactivating)}
      />
    </div>
  );
}
