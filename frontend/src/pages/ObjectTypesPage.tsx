import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, type FormEvent } from "react";
import { useOutletContext } from "react-router-dom";

import type { ConsoleContext } from "../App";
import {
  createObjectType,
  listBusinessRules,
  listObjectDirectory,
  listObjectTypes,
  listPolicyCategories,
  publishBusinessRule,
  publishRuleDraft,
  repealBusinessRule,
  rescopeBusinessRule,
  updateObjectType,
  type BusinessRule,
  type EntityKind,
  type ObjectTypeDefinition,
  type ObjectTypeStatus,
  type RuleKind,
} from "../api/configuration";
import { Drawer } from "../components/master-data/Drawer";
import { apiErrorMessage, ListState, StatusBadge } from "../components/master-data/ListState";
import { Pagination } from "../components/master-data/Pagination";
import { hasCapability } from "../components/AppShell";
import { RULE_KINDS, SCOPED_RULE_KINDS, ruleKindHint, ruleKindLabel, ruleKindPlaceholder } from "../components/rules";
import { useI18n } from "../i18n";
import "./configuration.css";

const PAGE_SIZE = 20;
const EMPTY_SCHEMA = JSON.stringify({ type: "object", required: [], properties: {} }, null, 2);

type TypeForm = {
  objectType: string;
  entityKind: EntityKind;
  title: string;
  description: string;
  schema: string;
  stateMachine: string;
};

type ScopedKind = (typeof SCOPED_RULE_KINDS)[number];

type RuleForm = {
  kind: RuleKind;
  entityKind: EntityKind;
  objectType: string;
  name: string;
  // a policy's own identity; unused by the scoped kinds
  code: string;
  category: string;
  title: string;
  effectiveFrom: string;
  body: string;
};

/** The three acts a published rule still takes — release a draft, close it,
 *  change who reads it — each a short second drawer, never an edit. */
type RuleAct =
  | { action: "publish"; rule: BusinessRule; effectiveFrom: string; note: string }
  | { action: "repeal"; rule: BusinessRule; effectiveThru: string; note: string }
  | { action: "visibility"; rule: BusinessRule; visibility: "internal" | "restricted" | "public"; requiredCapability: string; note: string };

function blankType(): TypeForm {
  return {
    objectType: "",
    entityKind: "business_object",
    title: "",
    description: "",
    schema: EMPTY_SCHEMA,
    stateMachine: "",
  };
}

function typeForm(definition: ObjectTypeDefinition): TypeForm {
  return {
    objectType: definition.object_type,
    entityKind: definition.entity_kind,
    title: definition.title ?? "",
    description: definition.description ?? "",
    schema: JSON.stringify(definition.json_schema, null, 2),
    stateMachine: definition.state_machine ? JSON.stringify(definition.state_machine, null, 2) : "",
  };
}

function parseObject(
  value: string,
  label: string,
  optional = false,
  localize: (chinese: string, english: string) => string = (chinese) => chinese,
): Record<string, unknown> | null {
  if (optional && !value.trim()) return null;
  let parsed: unknown;
  try {
    parsed = JSON.parse(value);
  } catch {
    throw new Error(localize(`${label}格式不正确。`, `${label} has an invalid format.`));
  }
  if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
    throw new Error(localize(`${label}必须包含带名称的字段。`, `${label} must contain named fields.`));
  }
  return parsed as Record<string, unknown>;
}

function blankRule(kind: RuleKind): RuleForm {
  return { kind, entityKind: "business_object", objectType: "", name: "default", code: "", category: "", title: "", effectiveFrom: "", body: "" };
}

function isScopedKind(kind: RuleKind): kind is ScopedKind {
  return (SCOPED_RULE_KINDS as RuleKind[]).includes(kind);
}

/** Lines of the version in force that the draft drops, and lines it adds —
 *  enough to see that "add one rule" did not become "replace the document". */
export function ruleLineDiff(before: string, after: string): { removed: string[]; added: string[] } {
  const lines = (value: string) => new Set(value.split("\n").map((line) => line.trim()).filter(Boolean));
  const current = lines(before);
  const draft = lines(after);
  return {
    removed: [...current].filter((line) => !draft.has(line)),
    added: [...draft].filter((line) => !current.has(line)),
  };
}

export function ObjectTypesPage() {
  const { text } = useI18n();
  const context = useOutletContext<ConsoleContext | null>();
  const canEditTypes = Boolean(context?.bootstrap && hasCapability(context.bootstrap, "object_types.manage"));
  const canPublishRules = Boolean(context?.bootstrap && hasCapability(context.bootstrap, "workflows.publish"));
  const canPublishPolicies = Boolean(context?.bootstrap && hasCapability(context.bootstrap, "policy.publish"));
  const canActOn = (kind: RuleKind) => (kind === "policy" ? canPublishPolicies : canPublishRules);
  const queryClient = useQueryClient();
  const [keyword, setKeyword] = useState("");
  const [keywordDraft, setKeywordDraft] = useState("");
  const [status, setStatus] = useState<"" | ObjectTypeStatus>("");
  const [kind, setKind] = useState<"" | EntityKind>("");
  const [page, setPage] = useState(1);
  const [rulePage, setRulePage] = useState(1);
  const [ruleKind, setRuleKind] = useState<RuleKind>("approval_flow");
  const [showHistory, setShowHistory] = useState(false);
  const [editing, setEditing] = useState<ObjectTypeDefinition | null | undefined>(undefined);
  const [typeDraft, setTypeDraft] = useState<TypeForm>(blankType);
  const [typeValidation, setTypeValidation] = useState<string | null>(null);
  const [ruleOpen, setRuleOpen] = useState(false);
  const [ruleDraft, setRuleDraft] = useState<RuleForm>(() => blankRule("approval_flow"));
  const [bodyTouched, setBodyTouched] = useState(false);
  const [ruleValidation, setRuleValidation] = useState<string | null>(null);
  const [act, setAct] = useState<RuleAct | null>(null);

  const definitions = useQuery({
    queryKey: ["object-types", { keyword, status, kind, page }],
    queryFn: () => listObjectTypes({
      keyword: keyword || undefined,
      status: status || undefined,
      entity_kind: kind || undefined,
      page,
      size: PAGE_SIZE,
    }),
    placeholderData: keepPreviousData,
  });

  const rules = useQuery({
    queryKey: ["business-rules", { kind: ruleKind, page: rulePage, showHistory }],
    // in force by default; history adds the superseded, repealed and (for the kind's authors) draft versions
    queryFn: () => listBusinessRules({ kind: ruleKind, status: showHistory ? undefined : "published", page: rulePage, size: PAGE_SIZE }),
    placeholderData: keepPreviousData,
  });
  const ruleTargets = useQuery({
    queryKey: ["object-directory"],
    queryFn: listObjectDirectory,
    enabled: canPublishRules,
  });
  const categories = useQuery({
    queryKey: ["type-options", "policy_category"],
    queryFn: listPolicyCategories,
    enabled: canPublishPolicies && ruleOpen && ruleDraft.kind === "policy",
  });
  const isPolicy = ruleDraft.kind === "policy";
  // the version in force for the scope being edited — the editor starts from it
  const draftName = ruleDraft.name.trim() || "default";
  const current = useQuery({
    queryKey: ["business-rules", "current", ruleDraft.kind, ruleDraft.entityKind, ruleDraft.objectType, draftName, ruleDraft.code.trim()],
    // every version, newest first: the one in force if there is one, else the
    // draft the catalog seeded, so the editor never opens on a blank page
    queryFn: () => isPolicy
      ? listBusinessRules({ kind: "policy", code: ruleDraft.code.trim(), size: 5 })
      : listBusinessRules({ kind: ruleDraft.kind, entity_kind: ruleDraft.entityKind, object_type: ruleDraft.objectType, name: draftName, size: 5 }),
    enabled: ruleOpen && (isPolicy ? ruleDraft.code.trim().length > 0 : Boolean(ruleDraft.objectType)),
  });
  const currentRule = current.data?.data.find((r) => r.status === "published") ?? current.data?.data.find((r) => r.status === "draft") ?? null;
  const currentIsDraft = currentRule?.status === "draft";
  const diff = currentRule && ruleDraft.body.trim() !== currentRule.body.trim() ? ruleLineDiff(currentRule.body, ruleDraft.body) : null;
  const replacesEverything = Boolean(diff && diff.removed.length > 0 && ruleLineDiff(currentRule?.body ?? "", "").removed.length === diff.removed.length);
  useEffect(() => {
    if (!ruleOpen || bodyTouched || !current.isSuccess) return;
    const body = currentRule?.body ?? "";
    setRuleDraft((draft) => {
      // a policy's next version keeps its category and title unless retyped
      const next = { ...draft, body };
      if (currentRule?.kind === "policy") {
        if (!draft.category && currentRule.category) next.category = currentRule.category;
        if (!draft.title.trim() && currentRule.title) next.title = currentRule.title;
      }
      return draft.body === next.body && draft.category === next.category && draft.title === next.title ? draft : next;
    });
  }, [ruleOpen, bodyTouched, current.isSuccess, currentRule]);
  const publishableTargets = (ruleTargets.data ?? [])
    .filter((target) => target.definition_status === "active" ||
      (target.entity_kind === "business_object" && target.count > 0))
    .sort((left, right) => left.entity_kind.localeCompare(right.entity_kind) || left.object_type.localeCompare(right.object_type));

  useEffect(() => {
    const pages = definitions.data?.meta.pages;
    if (pages && page > pages) setPage(pages);
  }, [definitions.data?.meta.pages, page]);
  useEffect(() => {
    const pages = rules.data?.meta.pages;
    if (pages && rulePage > pages) setRulePage(pages);
  }, [rules.data?.meta.pages, rulePage]);

  const saveType = useMutation({
    mutationFn: async ({ current, draft }: { current: ObjectTypeDefinition | null; draft: TypeForm }) => {
      const schema = parseObject(draft.schema, text("字段规则", "Field rules"), false, text) ?? {};
      const stateMachine = parseObject(draft.stateMachine, text("状态流程", "Status flow"), true, text);
      const common = {
        title: draft.title.trim() || null,
        description: draft.description.trim() || null,
        json_schema: schema,
        state_machine: stateMachine,
      };
      return current
        ? updateObjectType(current.id, common)
        : createObjectType({
            ...common,
            object_type: draft.objectType.trim(),
            entity_kind: draft.entityKind,
          });
    },
    onSuccess: async () => {
      setEditing(undefined);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["object-types"] }),
        queryClient.invalidateQueries({ queryKey: ["capabilities"] }),
        queryClient.invalidateQueries({ queryKey: ["object-directory"] }),
        queryClient.invalidateQueries({ queryKey: ["objects", "directory"] }),
      ]);
    },
  });

  const changeStatus = useMutation({
    mutationFn: ({ id, status: next }: { id: string; status: ObjectTypeStatus }) =>
      updateObjectType(id, { status: next }),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["object-types"] }),
        queryClient.invalidateQueries({ queryKey: ["capabilities"] }),
        queryClient.invalidateQueries({ queryKey: ["object-directory"] }),
        queryClient.invalidateQueries({ queryKey: ["objects", "directory"] }),
      ]);
    },
  });

  const publish = useMutation({
    mutationFn: () => publishBusinessRule(isPolicy ? {
      kind: "policy",
      code: ruleDraft.code.trim(),
      category: ruleDraft.category,
      title: ruleDraft.title.trim(),
      body: ruleDraft.body.trim(),
      ...(ruleDraft.effectiveFrom ? { effective_from: ruleDraft.effectiveFrom } : {}),
    } : {
      kind: ruleDraft.kind,
      entity_kind: ruleDraft.entityKind,
      object_type: ruleDraft.objectType.trim(),
      name: draftName,
      body: ruleDraft.body.trim(),
    }),
    onSuccess: async () => {
      setRuleOpen(false);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["business-rules"] }),
        queryClient.invalidateQueries({ queryKey: ["objects", "directory"] }),
      ]);
    },
  });

  const openCreate = () => {
    setTypeDraft(blankType());
    setTypeValidation(null);
    saveType.reset();
    setEditing(null);
  };

  const openEdit = (definition: ObjectTypeDefinition) => {
    setTypeDraft(typeForm(definition));
    setTypeValidation(null);
    saveType.reset();
    setEditing(definition);
  };

  const submitType = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!editing && !typeDraft.objectType.trim()) {
      setTypeValidation(text("对象类型不能为空。", "Object type is required."));
      return;
    }
    if (typeDraft.entityKind === "builtin" && !typeDraft.stateMachine.trim()) {
      setTypeValidation(text("内置实体必须提供状态机定义。", "Built-in entities require a state-machine definition."));
      return;
    }
    try {
      parseObject(typeDraft.schema, text("字段规则", "Field rules"), false, text);
      parseObject(typeDraft.stateMachine, text("状态流程", "Status flow"), true, text);
    } catch (error) {
      setTypeValidation(apiErrorMessage(error));
      return;
    }
    setTypeValidation(null);
    saveType.mutate({ current: editing ?? null, draft: typeDraft });
  };

  const perform = useMutation({
    mutationFn: (current: RuleAct): Promise<unknown> => current.action === "publish"
      ? publishRuleDraft(current.rule.id, { ...(current.effectiveFrom ? { effective_from: current.effectiveFrom } : {}), ...(current.note.trim() ? { note: current.note.trim() } : {}) })
      : current.action === "repeal"
      ? repealBusinessRule(current.rule.id, { ...(current.effectiveThru ? { effective_thru: current.effectiveThru } : {}), ...(current.note.trim() ? { note: current.note.trim() } : {}) })
      : rescopeBusinessRule(current.rule.id, {
          visibility: current.visibility,
          required_capability: current.visibility === "restricted" ? current.requiredCapability.trim() : null,
          ...(current.note.trim() ? { note: current.note.trim() } : {}),
        }),
    onSuccess: async () => {
      setAct(null);
      await queryClient.invalidateQueries({ queryKey: ["business-rules"] });
    },
  });
  const openAct = (action: RuleAct["action"], rule: BusinessRule) => {
    perform.reset();
    if (action === "publish") setAct({ action, rule, effectiveFrom: "", note: "" });
    else if (action === "repeal") setAct({ action, rule, effectiveThru: "", note: "" });
    else setAct({ action, rule, visibility: rule.visibility as "internal" | "restricted" | "public", requiredCapability: rule.required_capability ?? "", note: "" });
  };
  const submitAct = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!act) return;
    if (act.action === "visibility" && act.visibility === "restricted" && !act.requiredCapability.trim()) return;
    perform.mutate(act);
  };

  const openRule = () => {
    const first = publishableTargets[0];
    const blank = blankRule(canPublishRules ? (isScopedKind(ruleKind) ? ruleKind : "approval_flow") : "policy");
    setRuleDraft(first ? { ...blank, entityKind: first.entity_kind, objectType: first.object_type } : blank);
    setBodyTouched(false);
    setRuleValidation(null);
    publish.reset();
    setRuleOpen(true);
  };

  const submitRule = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (isPolicy) {
      if (!ruleDraft.code.trim() || !ruleDraft.category || !ruleDraft.title.trim() || !ruleDraft.body.trim()) {
        setRuleValidation(text("制度需要编号、分类、标题和正文。", "A policy needs a code, a category, a title and its text."));
        return;
      }
    } else if (!ruleDraft.objectType.trim() || !ruleDraft.body.trim()) {
      setRuleValidation(text("对象类型和规则正文不能为空。", "Object type and rule text are required."));
      return;
    }
    setRuleValidation(null);
    publish.mutate();
  };

  return (
    <div className="configuration-page" data-testid="object-types-page">
      <header className="page-intro">
        <div>
          <span className="eyebrow">{text("对象与规则", "Objects & rules")}</span>
          <h2>{text("对象类型与业务规则", "Object types & business rules")}</h2>
          <p>{text("用字段规则约束业务对象，并发布 agent 读取的业务规则：审批流程、数据要求、单据联动。", "Set field rules for business objects and publish the business rules agents read: approval flows, data rules, linkages.")}</p>
        </div>
        <div className="page-actions">
          {(canPublishRules || canPublishPolicies) && <button className="button" type="button" onClick={openRule}>{text("发布规则", "Publish rule")}</button>}
          {canEditTypes && <button className="button primary" type="button" onClick={openCreate}>{text("定义类型", "Define type")}</button>}
        </div>
      </header>

      {!canEditTypes && !canPublishRules && <aside className="info-banner"><strong>{text("只读配置视图。", "Read-only configuration view.")}</strong><span>{text("当前角色可以审阅定义，但不能修改类型或发布规则。", "The current role can review definitions but cannot modify types or publish rules.")}</span></aside>}

      <section className="data-panel" aria-label={text("对象类型定义", "Object type definitions")}>
        <header className="section-bar">
          <div><strong>{text("类型定义", "Type definitions")}</strong><small>{text("读写时实时校验；归档不会删除历史记录。", "Definitions are validated on read and write; archiving preserves history.")}</small></div>
          <form className="compact-filters" onSubmit={(event) => { event.preventDefault(); setKeyword(keywordDraft.trim()); setPage(1); }}>
            <input aria-label={text("搜索对象类型", "Search object types")} placeholder={text("搜索类型或标题", "Search type or title")} value={keywordDraft} onChange={(e) => setKeywordDraft(e.target.value)} />
            <select aria-label={text("实体种类", "Entity kind")} value={kind} onChange={(e) => { setKind(e.target.value as "" | EntityKind); setPage(1); }}>
              <option value="">{text("全部种类", "All kinds")}</option><option value="business_object">{text("业务对象", "Business object")}</option><option value="builtin">{text("内置实体", "Built-in entity")}</option>
            </select>
            <select aria-label={text("类型状态", "Type status")} value={status} onChange={(e) => { setStatus(e.target.value as "" | ObjectTypeStatus); setPage(1); }}>
              <option value="">{text("全部状态", "All statuses")}</option><option value="active">{text("启用", "Active")}</option><option value="archived">{text("已归档", "Archived")}</option>
            </select>
            <button className="button compact" type="submit">{text("筛选", "Filter")}</button>
          </form>
        </header>
        {changeStatus.isError && <div className="panel-error" role="alert">{apiErrorMessage(changeStatus.error)}</div>}
        <ListState
          loading={definitions.isPending}
          error={definitions.isError ? apiErrorMessage(definitions.error) : null}
          empty={Boolean(definitions.data && definitions.data.data.length === 0)}
          emptyTitle={text("还没有对象类型", "No object types yet")}
          emptyDescription={text("创建第一个类型后，可为其配置字段规则与业务规则。", "Create the first type to configure its field rules and business rules.")}
          onRetry={() => void definitions.refetch()}
        >
          {definitions.data && <>
            <div className="table-scroll"><table className="data-table configuration-table">
              <thead><tr><th>{text("对象类型", "Object type")}</th><th>{text("种类", "Kind")}</th><th>{text("版本", "Version")}</th><th>{text("状态", "Status")}</th><th>{text("定义", "Definition")}</th><th><span className="sr-only">{text("操作", "Actions")}</span></th></tr></thead>
              <tbody>{definitions.data.data.map((item) => <tr key={item.id}>
                <td><strong>{item.title || item.object_type}</strong><small className="mono-cell">{item.object_type}</small></td>
                <td>{item.entity_kind === "builtin" ? text("内置实体", "Built-in entity") : text("业务对象", "Business object")}</td>
                <td><span className="version-chip">v{item.version}</span></td>
                <td><StatusBadge status={item.status} /></td>
                <td><details><summary>{text("查看详细内容", "View details")}</summary><pre>{JSON.stringify(item.json_schema, null, 2)}</pre></details></td>
                <td className="row-actions">
                  {canEditTypes && <><button className="text-action" type="button" onClick={() => openEdit(item)}>{text("编辑", "Edit")}</button>
                  <button
                    className={`text-action ${item.status === "active" ? "danger-text" : ""}`}
                    type="button"
                    disabled={changeStatus.isPending}
                    onClick={() => changeStatus.mutate({ id: item.id, status: item.status === "active" ? "archived" : "active" })}
                  >{item.status === "active" ? text("归档", "Archive") : text("恢复", "Restore")}</button></>}
                </td>
              </tr>)}</tbody>
            </table></div>
            <Pagination meta={definitions.data.meta} onPageChange={setPage} />
          </>}
        </ListState>
      </section>

      <section className="data-panel" aria-label={text("业务规则", "Business rules")}>
        <header className="section-bar">
          <div><strong>{text("业务规则", "Business rules")}</strong><small>{text("发布新版本会在同一事务里关闭上一版；agent 读取当前生效的版本。草稿可直接发布，生效版本可废止或改可见性，都不改一个字。", "Publishing a new version closes the previous one in the same transaction; agents read the version in force. A draft can be released as it stands, and a version in force repealed or re-scoped — none of it edits a word.")}</small></div>
          <div className="compact-filters">
            <select aria-label={text("规则种类", "Rule kind")} value={ruleKind} onChange={(e) => { setRuleKind(e.target.value as RuleKind); setRulePage(1); }}>
              {RULE_KINDS.map((kind) => <option key={kind} value={kind}>{ruleKindLabel(kind, text)}</option>)}
            </select>
            <label className="history-toggle"><input type="checkbox" checked={showHistory} onChange={(e) => { setShowHistory(e.target.checked); setRulePage(1); }} />{text("显示历史版本", "Show version history")}</label>
          </div>
        </header>
        <ListState
          loading={rules.isPending}
          error={rules.isError ? apiErrorMessage(rules.error) : null}
          empty={Boolean(rules.data && rules.data.data.length === 0)}
          emptyTitle={text(`还没有${ruleKindLabel(ruleKind, text)}`, `No ${ruleKindLabel(ruleKind, text).toLocaleLowerCase()} yet`)}
          emptyDescription={ruleKind === "policy"
            ? text("制度由制度管理员通过 agent 起草并发布。", "Policies are drafted and published by the policy administrators through their agent.")
            : text("发布后 agent 就按生效版本读取。", "Once published, agents read the version in force.")}
          onRetry={() => void rules.refetch()}
        >
          {rules.data && <>
            <div className="table-scroll"><table className="data-table configuration-table">
              <thead><tr><th>{text("适用于", "Applies to")}</th><th>{text("名称", "Name")}</th><th>{text("版本", "Version")}</th><th>{text("状态", "Status")}</th><th>{text("生效", "In force")}</th><th>{text("规则", "Rule")}</th><th>{text("发布人", "Published by")}</th><th><span className="sr-only">{text("操作", "Actions")}</span></th></tr></thead>
              <tbody>{rules.data.data.map((item) => <tr key={item.id}>
                <td><strong>{item.object_type ?? item.code}</strong><small>{item.object_type ? (item.entity_kind === "builtin" ? text("内置实体", "Built-in entity") : text("业务对象", "Business object")) : item.category}</small></td>
                <td>{item.object_type ? item.name : item.title}</td><td><span className="version-chip">v{item.version}</span></td>
                <td><StatusBadge status={item.status} /></td>
                <td>{item.effective_from ?? "—"}{item.effective_thru ? ` ${text("至", "to")} ${item.effective_thru}` : ""}</td>
                <td><details><summary>{text("查看规则", "View rule")}</summary><pre className="workflow-preview">{item.body}</pre></details></td>
                <td className="mono-cell">{item.published_by || item.created_by || "—"}</td>
                <td className="row-actions">
                  {canActOn(item.kind) && item.status === "draft" && <button className="text-action" type="button" onClick={() => openAct("publish", item)}>{text("发布", "Publish")}</button>}
                  {canActOn(item.kind) && item.status === "published" && <button className="text-action danger-text" type="button" onClick={() => openAct("repeal", item)}>{text("废止", "Repeal")}</button>}
                  {canActOn(item.kind) && item.status !== "draft" && <button className="text-action" type="button" onClick={() => openAct("visibility", item)}>{text("可见性", "Visibility")}</button>}
                </td>
              </tr>)}</tbody>
            </table></div>
            <Pagination meta={rules.data.meta} onPageChange={setRulePage} />
          </>}
        </ListState>
      </section>

      <Drawer
        open={editing !== undefined}
        title={editing ? text("编辑对象类型", "Edit object type") : text("定义对象类型", "Define object type")}
        description={editing ? text(`${editing.object_type} · 当前 v${editing.version}`, `${editing.object_type} · current v${editing.version}`) : text("定义对象种类、字段规则与可选状态流程。", "Define the object kind, field rules, and an optional status flow.")}
        submitLabel={editing ? text("保存定义", "Save definition") : text("创建定义", "Create definition")}
        busy={saveType.isPending}
        error={typeValidation || (saveType.isError ? apiErrorMessage(saveType.error) : null)}
        onClose={() => !saveType.isPending && setEditing(undefined)}
        onSubmit={submitType}
      >
        <div className="field-grid">
          <div className="field"><label htmlFor="type-kind">{text("实体种类", "Entity kind")}</label><select id="type-kind" disabled={Boolean(editing)} value={typeDraft.entityKind} onChange={(e) => setTypeDraft({ ...typeDraft, entityKind: e.target.value as EntityKind })}><option value="business_object">{text("业务对象", "Business object")}</option><option value="builtin">{text("内置实体", "Built-in entity")}</option></select></div>
          <div className="field"><label htmlFor="type-name">{text("对象类型", "Object type")} <b>*</b></label><input id="type-name" required disabled={Boolean(editing)} maxLength={100} value={typeDraft.objectType} onChange={(e) => setTypeDraft({ ...typeDraft, objectType: e.target.value })} /></div>
          <div className="field span-2"><label htmlFor="type-title">{text("显示标题", "Display title")}</label><input id="type-title" maxLength={200} value={typeDraft.title} onChange={(e) => setTypeDraft({ ...typeDraft, title: e.target.value })} /></div>
          <div className="field span-2"><label htmlFor="type-description">{text("说明", "Description")}</label><textarea id="type-description" rows={3} maxLength={2000} value={typeDraft.description} onChange={(e) => setTypeDraft({ ...typeDraft, description: e.target.value })} /></div>
          <div className="field span-2"><label htmlFor="type-schema">{text("字段规则", "Field rules")} <b>*</b></label><textarea id="type-schema" className="code-editor" rows={12} value={typeDraft.schema} onChange={(e) => setTypeDraft({ ...typeDraft, schema: e.target.value })} /></div>
          <div className="field span-2"><label htmlFor="type-machine">{text("状态流程", "Status flow")} {typeDraft.entityKind === "builtin" && <b>*</b>}</label><textarea id="type-machine" className="code-editor" rows={9} placeholder={typeDraft.entityKind === "builtin" ? text("内置对象必须填写状态流程设置", "A status flow is required for built-in objects") : text("可选状态流程设置", "Optional status flow")} value={typeDraft.stateMachine} onChange={(e) => setTypeDraft({ ...typeDraft, stateMachine: e.target.value })} /></div>
        </div>
      </Drawer>

      <Drawer
        open={ruleOpen}
        title={text("发布业务规则", "Publish business rule")}
        description={text("发布即生效：新版本开始，上一版在同一事务里关闭；历史版本全部保留。", "Publishing takes effect at once: the new version starts and the previous one closes in the same transaction; every version is kept.")}
        submitLabel={text("发布新版本", "Publish new version")}
        busy={publish.isPending}
        submitDisabled={!isPolicy && (ruleTargets.isPending || ruleTargets.isError || publishableTargets.length === 0)}
        error={ruleValidation || (!isPolicy && ruleTargets.isError ? text("对象目录加载失败，请重试后再发布规则。", "The object directory could not be loaded. Retry before publishing the rule.") : publish.isError ? apiErrorMessage(publish.error) : null)}
        onClose={() => !publish.isPending && setRuleOpen(false)}
        onSubmit={submitRule}
      >
        <div className="field-grid">
          <div className="field"><label htmlFor="rule-kind">{text("规则种类", "Rule kind")}</label><select id="rule-kind" value={ruleDraft.kind} onChange={(e) => { setRuleDraft({ ...ruleDraft, kind: e.target.value as RuleKind }); setBodyTouched(false); }}>{[...(canPublishRules ? SCOPED_RULE_KINDS : []), ...(canPublishPolicies ? (["policy"] as RuleKind[]) : [])].map((kind) => <option key={kind} value={kind}>{ruleKindLabel(kind, text)}</option>)}</select></div>
          {isPolicy ? <>
            <div className="field"><label htmlFor="rule-code">{text("制度编号", "Policy code")} <b>*</b></label><input id="rule-code" required maxLength={50} placeholder="HR-001" value={ruleDraft.code} onChange={(e) => { setRuleDraft({ ...ruleDraft, code: e.target.value }); setBodyTouched(false); }} /><small>{text("沿用已有编号即发布它的下一版。", "Reusing a code publishes that policy's next version.")}</small></div>
            <div className="field"><label htmlFor="rule-category">{text("分类", "Category")} <b>*</b></label><select id="rule-category" required value={ruleDraft.category} onChange={(e) => setRuleDraft({ ...ruleDraft, category: e.target.value })}><option value="">{text("选择分类", "Select a category")}</option>{(categories.data ?? []).filter((c) => c.is_active !== false).map((c) => <option key={c.id} value={c.name}>{c.title || c.name}</option>)}</select></div>
            <div className="field"><label htmlFor="rule-title">{text("标题", "Title")} <b>*</b></label><input id="rule-title" required maxLength={200} value={ruleDraft.title} onChange={(e) => setRuleDraft({ ...ruleDraft, title: e.target.value })} /></div>
            <div className="field"><label htmlFor="rule-effective">{text("生效日", "In force from")}</label><input id="rule-effective" type="date" value={ruleDraft.effectiveFrom} onChange={(e) => setRuleDraft({ ...ruleDraft, effectiveFrom: e.target.value })} /><small>{text("留空即今天；上一版在前一天关闭。", "Empty means today; the previous version closes the day before.")}</small></div>
          </> : <>
          <div className="field"><label htmlFor="rule-name">{text("规则名称", "Rule name")}</label><input id="rule-name" maxLength={100} value={ruleDraft.name} onChange={(e) => { setRuleDraft({ ...ruleDraft, name: e.target.value }); setBodyTouched(false); }} /></div>
          <div className="field span-2"><label htmlFor="rule-type">{text("对象类型", "Object type")} <b>*</b></label><select id="rule-type" required disabled={ruleTargets.isPending || ruleTargets.isError} value={ruleDraft.objectType ? `${ruleDraft.entityKind}:${ruleDraft.objectType}` : ""} onChange={(e) => { const selected = publishableTargets.find((target) => `${target.entity_kind}:${target.object_type}` === e.target.value); if (selected) { setRuleDraft({ ...ruleDraft, entityKind: selected.entity_kind, objectType: selected.object_type }); setBodyTouched(false); } }}><option value="">{text("选择已知对象类型", "Select a known object type")}</option><optgroup label={text("内置实体", "Built-in entities")}>{publishableTargets.filter((target) => target.entity_kind === "builtin").map((target) => <option key={`builtin:${target.object_type}`} value={`builtin:${target.object_type}`}>{text(`${target.title || target.object_type}（${target.count} 条）`, `${target.title || target.object_type} (${target.count} records)`)}</option>)}</optgroup><optgroup label={text("业务对象", "Business objects")}>{publishableTargets.filter((target) => target.entity_kind === "business_object").map((target) => <option key={`business_object:${target.object_type}`} value={`business_object:${target.object_type}`}>{text(`${target.title || target.object_type}（${target.count} 条）`, `${target.title || target.object_type} (${target.count} records)`)}</option>)}</optgroup></select>{ruleTargets.isPending && <small>{text("正在加载对象目录…", "Loading object directory…")}</small>}{ruleTargets.isError && <small className="field-error">{text("对象目录不可用。", "Object directory is unavailable.")}<button className="inline-retry" type="button" onClick={() => void ruleTargets.refetch()}>{text("重试", "Retry")}</button></small>}</div>
          </>}
          <div className="field span-2"><label htmlFor="rule-body">{text("规则正文", "Rule text")} <b>*</b></label><textarea id="rule-body" className="code-editor" rows={14} required value={ruleDraft.body} onChange={(e) => { setRuleDraft({ ...ruleDraft, body: e.target.value }); setBodyTouched(true); }} placeholder={ruleKindPlaceholder(ruleDraft.kind, text)} /><small>{ruleKindHint(ruleDraft.kind, text)}{currentRule && !currentIsDraft && <> {text(`已载入当前生效的 v${currentRule.version}；发布后成为 v${currentRule.version + 1}。`, `Loaded v${currentRule.version}, now in force; publishing makes it v${currentRule.version + 1}.`)}</>}{currentRule && currentIsDraft && <> {text(`已载入${currentRule.origin === "catalog" ? "出厂" : ""}草稿 v${currentRule.version}（尚未生效）；读一遍，改掉不是你们的句子，发布后即为 v${currentRule.version}。`, `Loaded the ${currentRule.origin === "catalog" ? "seeded " : ""}draft v${currentRule.version} (not in force); read it, change what is not yours, and publishing makes it v${currentRule.version}.`)}</>}</small></div>
          {diff && currentRule && <div className="field span-2 rule-diff" role="status" aria-label={text("与当前版本的差异", "Difference from the current version")}>
            <small>{text(`相对${currentIsDraft ? "草稿" : ""} v${currentRule.version}：删去 ${diff.removed.length} 行，新增 ${diff.added.length} 行。`, `Against ${currentIsDraft ? "draft " : ""}v${currentRule.version}: ${diff.removed.length} line(s) removed, ${diff.added.length} added.`)}{replacesEverything && <strong className="field-error"> {text("这会整篇替换当前版本——只是加一条规则的话，请保留原文。", "This replaces the whole current version — to add one rule, keep the existing text.")}</strong>}</small>
            {diff.removed.length > 0 && <pre className="workflow-preview rule-diff-removed">{diff.removed.map((line) => `- ${line}`).join("\n")}</pre>}
            {diff.added.length > 0 && <pre className="workflow-preview rule-diff-added">{diff.added.map((line) => `+ ${line}`).join("\n")}</pre>}
          </div>}
        </div>
      </Drawer>

      <Drawer
        open={act !== null}
        title={act?.action === "publish" ? text("发布草稿", "Publish draft") : act?.action === "repeal" ? text("废止规则", "Repeal rule") : text("更改可见性", "Change visibility")}
        description={act ? text(`${ruleKindLabel(act.rule.kind, text)} · ${act.rule.object_type ?? act.rule.code} · v${act.rule.version}`, `${ruleKindLabel(act.rule.kind, text)} · ${act.rule.object_type ?? act.rule.code} · v${act.rule.version}`) : ""}
        submitLabel={act?.action === "publish" ? text("发布", "Publish") : act?.action === "repeal" ? text("废止", "Repeal") : text("保存可见性", "Save visibility")}
        busy={perform.isPending}
        error={perform.isError ? apiErrorMessage(perform.error) : null}
        onClose={() => !perform.isPending && setAct(null)}
        onSubmit={submitAct}
      >
        {act && <div className="field-grid">
          {act.action === "publish" && <div className="field span-2"><label htmlFor="act-effective">{text("生效日", "In force from")}</label><input id="act-effective" type="date" value={act.effectiveFrom} onChange={(e) => setAct({ ...act, effectiveFrom: e.target.value })} /><small>{text("留空即今天；上一版在前一天关闭。发布的是草稿现在的文字——请先读一遍。", "Empty means today; the previous version closes the day before. What publishes is the draft's text as it stands — read it first.")}</small></div>}
          {act.action === "repeal" && <div className="field span-2"><label htmlFor="act-thru">{text("停止适用日", "Stops applying on")}</label><input id="act-thru" type="date" value={act.effectiveThru} onChange={(e) => setAct({ ...act, effectiveThru: e.target.value })} /><small>{text("留空即今天。废止不是删除：按日期仍可读到它曾经的规定。", "Empty means today. Repealing is not deleting: what it said stays readable by date.")}</small></div>}
          {act.action === "visibility" && <>
            <div className="field"><label htmlFor="act-visibility">{text("可见性", "Visibility")}</label><select id="act-visibility" value={act.visibility} onChange={(e) => setAct({ ...act, visibility: e.target.value as "internal" | "restricted" | "public" })}><option value="internal">{text("工作区内可读", "Anyone in the workspace")}</option><option value="restricted">{text("仅持有某能力者可读", "Holders of a capability only")}</option><option value="public">{text("公开", "Public")}</option></select></div>
            {act.visibility === "restricted" && <div className="field"><label htmlFor="act-capability">{text("所需能力", "Required capability")} <b>*</b></label><input id="act-capability" required placeholder="payroll.read" value={act.requiredCapability} onChange={(e) => setAct({ ...act, requiredCapability: e.target.value })} /></div>}
            <small className="span-2">{text("只改谁能读，不改一个字；被替代和已废止的版本同样适用。", "Changes who may read it and not a word of it; superseded and repealed versions too.")}</small>
          </>}
          <div className="field span-2"><label htmlFor="act-note">{text("备注", "Note")}</label><input id="act-note" maxLength={500} value={act.note} onChange={(e) => setAct({ ...act, note: e.target.value })} /></div>
        </div>}
      </Drawer>
    </div>
  );
}
