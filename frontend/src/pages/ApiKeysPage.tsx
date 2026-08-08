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
  if (!key.is_active) return { className: "inactive", label: text("密钥已停用", "Key disabled") };
  if (key.effective_active) return { className: "active", label: text("有效", "Valid") };
  if (!key.user_id || key.user_status === "active") return { className: "blocked", label: text("当前不可用", "Currently unavailable") };
  if (key.user_status === "disabled") return { className: "blocked", label: text("用户已停用", "User disabled") };
  if (key.user_status === "invited") return { className: "blocked", label: text("用户未激活", "User not activated") };
  return { className: "blocked", label: text("用户不存在", "User not found") };
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
      setValidation(text("标签不能超过 200 个字符。", "The label cannot exceed 200 characters."));
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
          <span className="eyebrow">{text("凭证", "Credentials")}</span>
          <h2>{text("访问凭证", "Access credentials")}</h2>
          <p>{text("公司凭证代表整个工作空间；个人凭证以该用户身份行动，并持续受其角色权限约束。", "Company credentials represent the workspace; personal credentials act as that user and remain subject to the user's current role permissions.")}</p>
        </div>
        <div className="page-actions"><a className="button" href="/web/connect">{text("连接新设备", "Connect new device")}</a><button className="button primary" type="button" disabled={Boolean(created)} title={created ? text("请先保存并关闭当前凭证", "Save and close the current credential first") : undefined} onClick={openCreate}>{text("创建凭证", "Create credential")}</button></div>
      </header>

      {created && <section className="secret-card" aria-labelledby="created-key-title">
        <div><span className="eyebrow" role="status" aria-live="polite">{text("凭证创建成功，仅显示一次", "Credential created — shown only once")}</span><h3 id="created-key-title">{text(`立即保存「${created.api_key.label || "未命名"}」的凭证`, `Save the credential for “${created.api_key.label || "Untitled"}” now`)}</h3><p>{text("关闭后无法再次查看；如果遗失，请停用它并创建新凭证。", "You cannot view it again after closing this panel. If it is lost, disable it and create a new credential.")}</p></div>
        <code tabIndex={0} aria-label={text("新创建的访问凭证；请主动复制并安全保存", "New access credential; copy and store it securely now")}>{created.plain_text_api_key}</code>
        <div><button className="button primary" type="button" onClick={() => void copySecret()}>{copyState === "copied" ? text("已复制", "Copied") : text("复制凭证", "Copy credential")}</button><button className="button quiet" type="button" onClick={dismissCreated}>{text("我已保存，关闭", "Saved — close")}</button></div>
        {copyState === "failed" && <small role="alert">{text("浏览器未允许自动复制，请手动选择凭证内容。", "The browser did not allow automatic copying. Select and copy the credential manually.")}</small>}
      </section>}

      {reactivate.isError && <div className="form-error" role="alert">{apiErrorMessage(reactivate.error)}</div>}

      <section className="data-panel" aria-label={text("访问凭证列表", "Access credential list")}>
        <header className="section-bar">
          <div><strong>{text("工作空间凭证", "Workspace credentials")}</strong><small>{text("停用立即生效；凭证内容不会在列表中再次显示。", "Disabling a credential takes effect immediately; its value is never shown again in this list.")}</small></div>
          <form className="compact-filters" onSubmit={(e) => { e.preventDefault(); setKeyword(keywordDraft.trim()); setPage(1); }}>
            <input aria-label={text("搜索访问凭证", "Search access credentials")} placeholder={text("搜索标签", "Search labels")} value={keywordDraft} onChange={(e) => setKeywordDraft(e.target.value)} />
            <select aria-label={text("凭证状态", "Credential status")} value={status} onChange={(e) => { setStatus(e.target.value as typeof status); setPage(1); }}><option value="">{text("全部状态", "All statuses")}</option><option value="active">{text("启用", "Active")}</option><option value="inactive">{text("停用", "Inactive")}</option></select>
            <button className="button compact" type="submit">{text("筛选", "Filter")}</button>
          </form>
        </header>
        <ListState
          loading={keys.isPending}
          error={keys.isError ? apiErrorMessage(keys.error) : null}
          empty={Boolean(keys.data && keys.data.data.length === 0)}
          emptyTitle={text("还没有访问凭证", "No access credentials yet")}
          emptyDescription={text("创建公司凭证，或为具体用户创建个人凭证。", "Create a company credential or a personal credential for a specific user.")}
          onRetry={() => void keys.refetch()}
        >
          {keys.data && <>
            <div className="table-scroll"><table className="data-table keys-table">
              <thead><tr><th>{text("标签", "Label")}</th><th>{text("类型", "Type")}</th><th>{text("身份", "Identity")}</th><th>{text("当前有效角色", "Current effective role")}</th><th>{text("状态", "Status")}</th><th>{text("创建时间", "Created")}</th><th><span className="sr-only">{text("操作", "Actions")}</span></th></tr></thead>
              <tbody>{keys.data.data.map((key) => {
                const availability = keyAvailability(key, text);
                return <tr key={key.id}>
                <td><strong>{key.label || text("未命名", "Untitled")}</strong><small className="mono-cell">{key.id.slice(0, 8)}…</small></td>
                <td><span className={`key-kind ${key.user_id ? "user" : "service"}`}>{key.user_id ? text("个人", "Personal") : text("公司", "Company")}</span></td>
                <td>{key.user_id ? <><strong>{key.user_name || key.user_email || text("已删除用户", "Deleted user")}</strong><small className="mono-cell">{key.user_email || `${key.user_id.slice(0, 8)}…`}</small></> : <span className="muted-value">{text("整个工作空间", "Entire workspace")}</span>}</td>
                <td>{key.effective_role
                  ? <><strong className="mono-cell">{key.effective_role}</strong>{key.user_id && key.role !== key.effective_role && <small>{text("签发时：", "Issued as: ")}{key.role}</small>}</>
                  : <><span className="muted-value">{text("无有效角色", "No effective role")}</span><small>{text("签发时：", "Issued as: ")}{key.role}</small></>}</td>
                <td><span className={`status-badge ${availability.className}`}>{availability.label}</span></td>
                <td>{new Intl.DateTimeFormat(language, { dateStyle: "medium" }).format(new Date(key.created_at))}</td>
                <td className="row-actions">{key.is_active
                  ? <button className="text-action danger-text" type="button" onClick={() => { deactivate.reset(); setDeactivating(key); }}>{text("停用", "Disable")}</button>
                  : <button className="text-action" type="button" disabled={reactivate.isPending} onClick={() => reactivate.mutate(key)}>{text("重新启用", "Re-enable")}</button>}
                </td>
              </tr>})}</tbody>
            </table></div>
            <Pagination meta={keys.data.meta} onPageChange={setPage} />
          </>}
        </ListState>
      </section>

      <Drawer
        open={createOpen}
        title={text("创建访问凭证", "Create access credential")}
        description={text("凭证只在创建成功后显示一次，请准备好安全的保存位置。", "The credential is shown only once after creation. Have a secure storage location ready.")}
        submitLabel={text("创建凭证", "Create credential")}
        busy={create.isPending}
        error={validation || (create.isError ? apiErrorMessage(create.error) : null)}
        onClose={() => !create.isPending && setCreateOpen(false)}
        onSubmit={submit}
      >
        <div className="field-grid">
          <div className="field span-2"><label htmlFor="key-label">{text("标签", "Label")}</label><input id="key-label" maxLength={200} value={label} onChange={(e) => setLabel(e.target.value)} /></div>
          <div className="field span-2 api-key-owner-field"><label htmlFor="key-user">{text("绑定用户（可选）", "Bind user (optional)")}</label>
            <div className="owner-search"><input aria-label={text("搜索可绑定用户", "Search eligible users")} placeholder={text("按姓名或邮箱搜索", "Search by name or email")} value={ownerKeywordDraft} onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); setOwnerKeyword(ownerKeywordDraft.trim()); setOwnerPage(1); } }} onChange={(e) => setOwnerKeywordDraft(e.target.value)} /><button className="button compact" type="button" onClick={() => { setOwnerKeyword(ownerKeywordDraft.trim()); setOwnerPage(1); }}>{text("搜索", "Search")}</button></div>
            <select id="key-user" value={userId} disabled={owners.isPending || owners.isError} onChange={(e) => { const id = e.target.value; setUserId(id); setSelectedOwner(ownerOptions.find((owner) => owner.id === id) ?? null); }}><option value="">{text("公司凭证", "Company credential")}</option>{ownerOptions.map((owner) => <option key={owner.id} value={owner.id}>{owner.name || owner.email} ({owner.role})</option>)}</select>
            {owners.isPending && <small>{text("正在加载可绑定用户…", "Loading eligible users…")}</small>}
            {owners.isError && <small className="field-error" role="alert">{text("用户目录暂时不可用；可以重试搜索，或创建公司凭证。", "The user directory is temporarily unavailable. Retry the search or create a company credential.")}</small>}
            {owners.data && <div className="owner-pagination"><span>{text(`共 ${owners.data.meta.total} 位活跃用户`, `${owners.data.meta.total} active users`)}</span><div><button type="button" className="text-action" disabled={ownerPage <= 1} onClick={() => setOwnerPage((current) => current - 1)}>{text("上一页", "Previous")}</button><span>{owners.data.meta.page} / {owners.data.meta.pages}</span><button type="button" className="text-action" disabled={ownerPage >= owners.data.meta.pages} onClick={() => setOwnerPage((current) => current + 1)}>{text("下一页", "Next")}</button></div></div>}
          </div>
          <aside className="key-explanation field span-2"><strong>{userId ? text("个人访问凭证", "Personal access credential") : text("工作空间访问凭证", "Workspace access credential")}</strong><p>{userId ? text("所有行为归属于所选用户，并实时继承其角色权限。", "Every action is attributed to the selected user and inherits that user's role permissions in real time.") : text("适合自动化代理与系统连接，代表整个工作空间执行操作。", "Suitable for automation agents and system connections acting for the whole workspace.")}</p></aside>
        </div>
      </Drawer>

      <ConfirmDialog
        open={deactivating !== null}
        title={text(`停用「${deactivating?.label || "未命名凭证"}」？`, `Disable “${deactivating?.label || "Untitled credential"}”?`)}
        description={text("依赖此凭证的代理与连接将立即无法访问 Oryh；管理员之后可以重新启用。", "Agents and connections that depend on this credential will immediately lose access to Oryh. An administrator can re-enable it later.")}
        kicker={text("凭证停用", "Disable credential")}
        confirmLabel={text("确认停用", "Disable credential")}
        busyLabel={text("正在停用…", "Disabling…")}
        busy={deactivate.isPending}
        error={deactivate.isError ? apiErrorMessage(deactivate.error) : null}
        onCancel={() => !deactivate.isPending && setDeactivating(null)}
        onConfirm={() => deactivating && deactivate.mutate(deactivating)}
      />
    </div>
  );
}
