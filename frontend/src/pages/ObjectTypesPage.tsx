import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, type FormEvent } from "react";
import { useOutletContext } from "react-router-dom";

import type { ConsoleContext } from "../App";
import {
  createObjectType,
  listObjectDirectory,
  listObjectTypes,
  listWorkflows,
  publishWorkflow,
  updateObjectType,
  type EntityKind,
  type ObjectTypeDefinition,
  type ObjectTypeStatus,
} from "../api/configuration";
import { Drawer } from "../components/master-data/Drawer";
import { apiErrorMessage, ListState, StatusBadge } from "../components/master-data/ListState";
import { Pagination } from "../components/master-data/Pagination";
import { hasCapability } from "../components/AppShell";
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

type WorkflowForm = {
  entityKind: EntityKind;
  objectType: string;
  name: string;
  definition: string;
};

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

function blankWorkflow(): WorkflowForm {
  return { entityKind: "business_object", objectType: "", name: "default", definition: "" };
}

export function ObjectTypesPage() {
  const { text } = useI18n();
  const context = useOutletContext<ConsoleContext | null>();
  const canEditTypes = Boolean(context?.bootstrap && hasCapability(context.bootstrap, "object_types.manage"));
  const canPublishWorkflows = Boolean(context?.bootstrap && hasCapability(context.bootstrap, "workflows.publish"));
  const queryClient = useQueryClient();
  const [keyword, setKeyword] = useState("");
  const [keywordDraft, setKeywordDraft] = useState("");
  const [status, setStatus] = useState<"" | ObjectTypeStatus>("");
  const [kind, setKind] = useState<"" | EntityKind>("");
  const [page, setPage] = useState(1);
  const [workflowPage, setWorkflowPage] = useState(1);
  const [showHistory, setShowHistory] = useState(false);
  const [editing, setEditing] = useState<ObjectTypeDefinition | null | undefined>(undefined);
  const [typeDraft, setTypeDraft] = useState<TypeForm>(blankType);
  const [typeValidation, setTypeValidation] = useState<string | null>(null);
  const [workflowOpen, setWorkflowOpen] = useState(false);
  const [workflowDraft, setWorkflowDraft] = useState<WorkflowForm>(blankWorkflow);
  const [workflowValidation, setWorkflowValidation] = useState<string | null>(null);

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

  const workflows = useQuery({
    queryKey: ["workflows", { page: workflowPage, showHistory }],
    queryFn: () => listWorkflows({ page: workflowPage, size: PAGE_SIZE, history: showHistory }),
    placeholderData: keepPreviousData,
  });
  const workflowTargets = useQuery({
    queryKey: ["object-directory"],
    queryFn: listObjectDirectory,
    enabled: canPublishWorkflows,
  });
  const publishableTargets = (workflowTargets.data ?? [])
    .filter((target) => target.definition_status === "active" ||
      (target.entity_kind === "business_object" && target.count > 0))
    .sort((left, right) => left.entity_kind.localeCompare(right.entity_kind) || left.object_type.localeCompare(right.object_type));

  useEffect(() => {
    const pages = definitions.data?.meta.pages;
    if (pages && page > pages) setPage(pages);
  }, [definitions.data?.meta.pages, page]);
  useEffect(() => {
    const pages = workflows.data?.meta.pages;
    if (pages && workflowPage > pages) setWorkflowPage(pages);
  }, [workflows.data?.meta.pages, workflowPage]);

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
    mutationFn: () => publishWorkflow({
      entity_kind: workflowDraft.entityKind,
      object_type: workflowDraft.objectType.trim(),
      name: workflowDraft.name.trim() || "default",
      definition_text: workflowDraft.definition.trim(),
    }),
    onSuccess: async () => {
      setWorkflowOpen(false);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["workflows"] }),
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

  const openWorkflow = () => {
    const first = publishableTargets[0];
    setWorkflowDraft(first ? {
      ...blankWorkflow(),
      entityKind: first.entity_kind,
      objectType: first.object_type,
    } : blankWorkflow());
    setWorkflowValidation(null);
    publish.reset();
    setWorkflowOpen(true);
  };

  const submitWorkflow = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!workflowDraft.objectType.trim() || !workflowDraft.definition.trim()) {
      setWorkflowValidation(text("对象类型和流程定义不能为空。", "Object type and workflow definition are required."));
      return;
    }
    setWorkflowValidation(null);
    publish.mutate();
  };

  return (
    <div className="configuration-page" data-testid="object-types-page">
      <header className="page-intro">
        <div>
          <span className="eyebrow">{text("规则与流程", "Rules & workflows")}</span>
          <h2>{text("对象类型与流程", "Object types & workflows")}</h2>
          <p>{text("用字段规则约束业务对象，并发布代理可执行的自然语言流程。", "Set field rules for business objects and publish natural-language workflows that agents can follow.")}</p>
        </div>
        <div className="page-actions">
          {canPublishWorkflows && <button className="button" type="button" onClick={openWorkflow}>{text("发布流程", "Publish workflow")}</button>}
          {canEditTypes && <button className="button primary" type="button" onClick={openCreate}>{text("定义类型", "Define type")}</button>}
        </div>
      </header>

      {!canEditTypes && !canPublishWorkflows && <aside className="info-banner"><strong>{text("只读配置视图。", "Read-only configuration view.")}</strong><span>{text("当前角色可以审阅定义，但不能修改类型或发布流程。", "The current role can review definitions but cannot modify types or publish workflows.")}</span></aside>}

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
          emptyDescription={text("创建第一个类型后，可为其配置字段规则与流程。", "Create the first type to configure its field rules and workflows.")}
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

      <section className="data-panel" aria-label={text("流程定义", "Workflow definitions")}>
        <header className="section-bar">
          <div><strong>{text("流程定义", "Workflow definitions")}</strong><small>{text("发布新版本会保留完整历史，活动版本供代理执行。", "Publishing a new version preserves the full history; agents execute the active version.")}</small></div>
          <label className="history-toggle"><input type="checkbox" checked={showHistory} onChange={(e) => { setShowHistory(e.target.checked); setWorkflowPage(1); }} />{text("显示历史版本", "Show version history")}</label>
        </header>
        <ListState
          loading={workflows.isPending}
          error={workflows.isError ? apiErrorMessage(workflows.error) : null}
          empty={Boolean(workflows.data && workflows.data.data.length === 0)}
          emptyTitle={text("还没有流程定义", "No workflow definitions yet")}
          emptyDescription={text("发布流程后，代理就能按版本追踪审批路由。", "Publish a workflow so agents can follow versioned approval routing.")}
          onRetry={() => void workflows.refetch()}
        >
          {workflows.data && <>
            <div className="table-scroll"><table className="data-table configuration-table">
              <thead><tr><th>{text("适用于", "Applies to")}</th><th>{text("名称", "Name")}</th><th>{text("版本", "Version")}</th><th>{text("状态", "Status")}</th><th>{text("流程", "Workflow")}</th><th>{text("发布人", "Published by")}</th></tr></thead>
              <tbody>{workflows.data.data.map((item) => <tr key={item.id}>
                <td><strong>{item.object_type}</strong><small>{item.entity_kind === "builtin" ? text("内置实体", "Built-in entity") : text("业务对象", "Business object")}</small></td>
                <td>{item.name}</td><td><span className="version-chip">v{item.version}</span></td>
                <td><StatusBadge status={item.status} /></td>
                <td><details><summary>{text("查看定义", "View definition")}</summary><pre className="workflow-preview">{item.definition_text}</pre></details></td>
                <td className="mono-cell">{item.created_by || "—"}</td>
              </tr>)}</tbody>
            </table></div>
            <Pagination meta={workflows.data.meta} onPageChange={setWorkflowPage} />
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
        open={workflowOpen}
        title={text("发布流程定义", "Publish workflow definition")}
        description={text("发布会创建新版本并保留所有旧版本，无法原地覆盖历史。", "Publishing creates a new version and preserves every previous version; history cannot be overwritten in place.")}
        submitLabel={text("发布新版本", "Publish new version")}
        busy={publish.isPending}
        submitDisabled={workflowTargets.isPending || workflowTargets.isError || publishableTargets.length === 0}
        error={workflowValidation || (workflowTargets.isError ? text("对象目录加载失败，请重试后再发布流程。", "The object directory could not be loaded. Retry before publishing the workflow.") : publish.isError ? apiErrorMessage(publish.error) : null)}
        onClose={() => !publish.isPending && setWorkflowOpen(false)}
        onSubmit={submitWorkflow}
      >
        <div className="field-grid">
          <div className="field"><label htmlFor="workflow-kind">{text("实体种类", "Entity kind")}</label><input id="workflow-kind" readOnly value={workflowDraft.entityKind === "builtin" ? text("内置实体", "Built-in entity") : text("业务对象", "Business object")} /></div>
          <div className="field"><label htmlFor="workflow-name">{text("流程名称", "Workflow name")}</label><input id="workflow-name" maxLength={100} value={workflowDraft.name} onChange={(e) => setWorkflowDraft({ ...workflowDraft, name: e.target.value })} /></div>
          <div className="field span-2"><label htmlFor="workflow-type">{text("对象类型", "Object type")} <b>*</b></label><select id="workflow-type" required disabled={workflowTargets.isPending || workflowTargets.isError} value={workflowDraft.objectType ? `${workflowDraft.entityKind}:${workflowDraft.objectType}` : ""} onChange={(e) => { const selected = publishableTargets.find((target) => `${target.entity_kind}:${target.object_type}` === e.target.value); if (selected) setWorkflowDraft({ ...workflowDraft, entityKind: selected.entity_kind, objectType: selected.object_type }); }}><option value="">{text("选择已知对象类型", "Select a known object type")}</option><optgroup label={text("内置实体", "Built-in entities")}>{publishableTargets.filter((target) => target.entity_kind === "builtin").map((target) => <option key={`builtin:${target.object_type}`} value={`builtin:${target.object_type}`}>{text(`${target.title || target.object_type}（${target.count} 条）`, `${target.title || target.object_type} (${target.count} records)`)}</option>)}</optgroup><optgroup label={text("业务对象", "Business objects")}>{publishableTargets.filter((target) => target.entity_kind === "business_object").map((target) => <option key={`business_object:${target.object_type}`} value={`business_object:${target.object_type}`}>{text(`${target.title || target.object_type}（${target.count} 条）`, `${target.title || target.object_type} (${target.count} records)`)}</option>)}</optgroup></select>{workflowTargets.isPending && <small>{text("正在加载对象目录…", "Loading object directory…")}</small>}{workflowTargets.isError && <small className="field-error">{text("对象目录不可用。", "Object directory is unavailable.")}<button className="inline-retry" type="button" onClick={() => void workflowTargets.refetch()}>{text("重试", "Retry")}</button></small>}</div>
          <div className="field span-2"><label htmlFor="workflow-definition">{text("自然语言流程", "Natural-language workflow")} <b>*</b></label><textarea id="workflow-definition" className="code-editor" rows={14} required value={workflowDraft.definition} onChange={(e) => setWorkflowDraft({ ...workflowDraft, definition: e.target.value })} placeholder={text("## 提交要求\n例：每条工时必须关联到具体项目任务；一周合计恰好 40 小时。\n\n## 流转规则\n例：提交后由直属经理审批，金额超过一万加签总经理。", "## Submission requirements\ne.g. every entry must reference a project task; the week must total exactly 40 hours.\n\n## Routing\ne.g. line manager approves first; add the GM above ¥10,000.")} /><small>{text("一份文档承载该对象的全部规则：「提交要求」由员工侧 agent 填写时核对、工作流 agent 路由前校准；「流转规则」仅工作流 agent 使用。", "One document carries all of this object's rules: submission requirements are checked by the member's agent while filling and calibrated by the flow agent before routing; routing rules are read by the flow agent only.")}</small></div>
        </div>
      </Drawer>
    </div>
  );
}
