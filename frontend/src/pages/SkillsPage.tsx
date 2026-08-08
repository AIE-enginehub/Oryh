import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";

import { listCapabilities } from "../api/client";
import {
  createSkill,
  getSkill,
  listSkills,
  setSkillStatus,
  updateSkill,
  type Skill,
  type SkillStatus,
  type SkillSummary,
} from "../api/configuration";
import { Drawer } from "../components/master-data/Drawer";
import { SkillAudiencePanel } from "../components/skills/SkillAudiencePanel";
import { apiErrorMessage, ListState, StatusBadge } from "../components/master-data/ListState";
import { Pagination } from "../components/master-data/Pagination";
import { useI18n } from "../i18n";
import "./configuration.css";
import "./skills.css";

const PAGE_SIZE = 20;
const NAME_PATTERN = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;
const ZH_SKILL_TEMPLATE = `---
name:
description: Use when …（写清触发场景与示例）
---

# 技能标题

一句话说明本技能做什么。

## Required Inputs

\`\`\`yaml
oryh:
  base_url: "{{ORYH_BASE_URL}}"
  api_key: "{{ORYH_API_KEY}}"
  employee_id: "{{EMPLOYEE_ID}}"
\`\`\`

## Steps

1. …
`;
const EN_SKILL_TEMPLATE = `---
name:
description: Describe when to use this skill, including examples
---

# Skill title

Describe what this skill does in one sentence.

## Required Inputs

\`\`\`yaml
oryh:
  base_url: "{{ORYH_BASE_URL}}"
  api_key: "{{ORYH_API_KEY}}"
  employee_id: "{{EMPLOYEE_ID}}"
\`\`\`

## Steps

1. …
`;

type SkillFile = { id: number; path: string; content: string };
type SkillForm = {
  name: string;
  title: string;
  description: string;
  requiredCapability: string;
  files: SkillFile[];
};

let nextFileId = 1;

function file(path: string, content: string): SkillFile {
  return { id: nextFileId++, path, content };
}

function blankSkill(template = ZH_SKILL_TEMPLATE): SkillForm {
  return { name: "", title: "", description: "", requiredCapability: "", files: [file("SKILL.md", template)] };
}

function skillForm(skill: Skill): SkillForm {
  return {
    name: skill.name,
    title: skill.title ?? "",
    description: skill.description ?? "",
    requiredCapability: skill.required_capability ?? "",
    files: Object.entries(skill.files).map(([path, content]) => file(path, content)),
  };
}

export function parseSkillRequiredCapability(skillMd: string): string | null {
  const lines = skillMd.split(/\r?\n/);
  if (!lines.length || lines[0].trim() !== "---") return null;

  let requiredCapability: string | null = null;
  for (const line of lines.slice(1)) {
    if (line.trim() === "---") break;
    const separator = line.indexOf(":");
    if (separator < 0 || line.slice(0, separator).trim() !== "required_capability") continue;
    requiredCapability = line.slice(separator + 1).trim() || null;
  }
  return requiredCapability;
}

/** One glance at who a skill reaches. A targeted skill with nobody named is
 *  worth calling out — it is a real state and it reaches no one. */
function audienceLabel(skill: SkillSummary, text: (zh: string, en: string) => string) {
  if (skill.distribution_mode !== "targeted") {
    return <span className="muted-value">{text("按能力", "By capability")}</span>;
  }
  const roles = skill.audience?.roles ?? [];
  const people = skill.audience?.user_count ?? 0;
  if (roles.length === 0 && people === 0) {
    return <span className="audience-empty">{text("定向 · 无人", "Targeted · nobody")}</span>;
  }
  const parts = [...roles];
  if (people > 0) parts.push(text(`${people} 人`, `${people} ${people === 1 ? "person" : "people"}`));
  return <span className="audience-chip">{parts.join(" · ")}</span>;
}

export function resolveSkillRequiredCapability(
  selectedCapability: string,
  selectionTouched: boolean,
  skillMd: string,
): string | null {
  const selected = selectedCapability.trim();
  if (selectionTouched || selected) return selected || null;
  return parseSkillRequiredCapability(skillMd);
}

export function SkillsPage() {
  const { text } = useI18n();
  const queryClient = useQueryClient();
  const [keyword, setKeyword] = useState("");
  const [keywordDraft, setKeywordDraft] = useState("");
  const [status, setStatus] = useState<SkillStatus | "all">("all");
  const [page, setPage] = useState(1);
  const [editing, setEditing] = useState<Skill | null | undefined>(undefined);
  const [draft, setDraft] = useState<SkillForm>(() => blankSkill(text(ZH_SKILL_TEMPLATE, EN_SKILL_TEMPLATE)));
  const [validation, setValidation] = useState<string | null>(null);
  const [loadingName, setLoadingName] = useState<string | null>(null);
  const [capabilitySelectionTouched, setCapabilitySelectionTouched] = useState(false);
  const editRequestId = useRef(0);

  const skills = useQuery({
    queryKey: ["skills", { keyword, status, page }],
    queryFn: () => listSkills({ keyword: keyword || undefined, status, page, size: PAGE_SIZE }),
    placeholderData: keepPreviousData,
  });
  const catalog = useQuery({ queryKey: ["capabilities"], queryFn: listCapabilities });

  useEffect(() => {
    const pages = skills.data?.meta.pages;
    if (pages && page > pages) setPage(pages);
  }, [page, skills.data?.meta.pages]);

  const capabilityOptions = useMemo(() => {
    if (!catalog.data) return [];
    const values: Array<{ value: string; label: string; group: string }> = [];
    for (const capability of catalog.data.capabilities) {
      if (capability.kind === "custom") {
        values.push({ value: capability.name, label: capability.title ? `${capability.name} — ${capability.title}` : capability.name, group: text("自定义能力", "Custom capabilities") });
      } else if (capability.scopable) {
        values.push({ value: `${capability.name}:*`, label: `${capability.name}:* — ${text("全部对象类型", "All object types")}`, group: text("作用域能力", "Scoped capabilities") });
        for (const objectType of catalog.data.object_types) {
          values.push({ value: `${capability.name}:${objectType}`, label: `${capability.name}:${objectType}`, group: text("作用域能力", "Scoped capabilities") });
        }
      } else {
        values.push({ value: capability.name, label: capability.title ? `${capability.name} — ${capability.title}` : capability.name, group: text("系统能力", "System capabilities") });
      }
    }
    return values;
  }, [catalog.data, text]);

  const loadSkill = useMutation({
    mutationFn: ({ name }: { name: string; requestId: number }) => getSkill(name),
    onMutate: ({ name }) => setLoadingName(name),
    onSuccess: (skill, variables) => {
      if (variables.requestId !== editRequestId.current) return;
      setDraft(skillForm(skill));
      setCapabilitySelectionTouched(false);
      setValidation(null);
      setEditing(skill);
    },
    onSettled: (_data, _error, variables) => {
      if (variables.requestId === editRequestId.current) setLoadingName(null);
    },
  });

  const save = useMutation({
    mutationFn: async ({ current, form, capabilityTouched }: { current: Skill | null; form: SkillForm; capabilityTouched: boolean }) => {
      const files = Object.fromEntries(form.files.map((item) => [item.path.trim(), item.content]));
      const common = {
        title: form.title.trim() || null,
        description: form.description.trim() || null,
        required_capability: resolveSkillRequiredCapability(
          form.requiredCapability,
          capabilityTouched,
          files["SKILL.md"] ?? "",
        ),
        files,
      };
      return current
        ? updateSkill(current.name, common)
        : createSkill({ ...common, name: form.name.trim() });
    },
    onSuccess: async () => {
      setEditing(undefined);
      await queryClient.invalidateQueries({ queryKey: ["skills"] });
    },
  });

  const toggle = useMutation({
    mutationFn: (skill: SkillSummary) => setSkillStatus(skill.name, skill.status === "active" ? "archived" : "active"),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["skills"] }),
  });

  const openCreate = () => {
    editRequestId.current += 1;
    setLoadingName(null);
    loadSkill.reset();
    setDraft(blankSkill(text(ZH_SKILL_TEMPLATE, EN_SKILL_TEMPLATE)));
    setCapabilitySelectionTouched(false);
    setValidation(null);
    save.reset();
    setEditing(null);
  };

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (catalog.isPending || catalog.isError) {
      setValidation(text("能力目录尚未就绪，请重试后再保存，避免意外改变技能分发范围。", "The capability catalog is not ready. Retry before saving to avoid changing the skill's distribution unexpectedly."));
      return;
    }
    const name = draft.name.trim();
    if (!editing && !NAME_PATTERN.test(name)) {
      setValidation(text("名称只能使用小写字母、数字和单个连字符，例如 daily-report-submit。", "Names may contain only lowercase letters, numbers, and single hyphens, for example daily-report-submit."));
      return;
    }
    const paths = draft.files.map((item) => item.path.trim());
    if (paths.some((path) => !path)) {
      setValidation(text("所有技能文件都必须填写相对路径。", "Every skill file must have a relative path."));
      return;
    }
    if (new Set(paths).size !== paths.length) {
      setValidation(text("技能文件路径不能重复。", "Skill file paths must be unique."));
      return;
    }
    if (!paths.includes("SKILL.md")) {
      setValidation(text("技能文件必须包含 SKILL.md。", "Skill files must include SKILL.md."));
      return;
    }
    if (paths.some((path) => path.startsWith("/") || path.includes("..") || path.includes("\\"))) {
      setValidation(text("文件必须使用安全的相对路径，不能包含 / 开头、.. 或反斜杠。", "Files must use safe relative paths and cannot start with / or contain .. or backslashes."));
      return;
    }
    setValidation(null);
    save.mutate({ current: editing ?? null, form: draft, capabilityTouched: capabilitySelectionTouched });
  };

  const changeFile = (id: number, fieldName: "path" | "content", value: string) => {
    setDraft((current) => ({
      ...current,
      files: current.files.map((item) => item.id === id ? { ...item, [fieldName]: value } : item),
    }));
  };

  const grouped = [text("系统能力", "System capabilities"), text("作用域能力", "Scoped capabilities"), text("自定义能力", "Custom capabilities")];
  const skillMarkdown = draft.files.find((item) => item.path.trim() === "SKILL.md")?.content ?? "";
  const frontmatterCapability = parseSkillRequiredCapability(skillMarkdown);
  const capabilitySelectValue = draft.requiredCapability ||
    (!capabilitySelectionTouched ? frontmatterCapability ?? "" : "");
  const capabilityStillKnown = !capabilitySelectValue ||
    capabilityOptions.some((option) => option.value === capabilitySelectValue);
  const catalogReady = !catalog.isPending && !catalog.isError;

  return (
    <div className="automation-page" data-testid="skills-page">
      <header className="page-intro">
        <div>
          <span className="eyebrow">{text("代理契约", "Agent contracts")}</span>
          <h2>{text("技能", "Skills")}</h2>
          <p>{text("按工作空间维护 AI 代理的流程说明、触发描述、文件内容与角色分发范围。", "Manage AI agent workflow instructions, trigger descriptions, files, and role-based distribution for this workspace.")}</p>
        </div>
        <button className="button primary" type="button" onClick={openCreate}>{text("新建技能", "New skill")}</button>
      </header>

      <aside className="info-banner">
        <strong>{text("分发和鉴权彼此独立。", "Distribution and authorization are independent.")}</strong>
        <span>{text("所需权限决定哪些角色收到技能；系统仍会按照同一权限核验每次操作。", "The required permission determines which roles receive a skill; Oryh checks every action against the same permission.")}</span>
      </aside>

      {((loadSkill.isError && loadSkill.variables?.requestId === editRequestId.current) || toggle.isError) && <div className="form-error" role="alert">{apiErrorMessage(loadSkill.isError && loadSkill.variables?.requestId === editRequestId.current ? loadSkill.error : toggle.error)}</div>}

      <section className="data-panel" aria-label={text("技能列表", "Skill list")}>
        <header className="section-bar">
          <div><strong>{text("技能目录", "Skill catalog")}</strong><small>{text("产品技能可保存为工作空间自定义版本，并保留历史版本。", "Product skills can be saved as workspace-specific versions with full version history.")}</small></div>
          <form className="compact-filters" onSubmit={(e) => { e.preventDefault(); setKeyword(keywordDraft.trim()); setPage(1); }}>
            <input aria-label={text("搜索技能", "Search skills")} placeholder={text("搜索名称或说明", "Search name or description")} value={keywordDraft} onChange={(e) => setKeywordDraft(e.target.value)} />
            <select aria-label={text("技能状态", "Skill status")} value={status} onChange={(e) => { setStatus(e.target.value as SkillStatus | "all"); setPage(1); }}><option value="all">{text("全部状态", "All statuses")}</option><option value="active">{text("启用", "Active")}</option><option value="archived">{text("已归档", "Archived")}</option></select>
            <button className="button compact" type="submit">{text("筛选", "Filter")}</button>
          </form>
        </header>
        <ListState
          loading={skills.isPending}
          error={skills.isError ? apiErrorMessage(skills.error) : null}
          empty={Boolean(skills.data && skills.data.data.length === 0)}
          emptyTitle={text("还没有技能", "No skills yet")}
          emptyDescription={text("创建第一份 SKILL.md，让代理获得明确、可审计的工作流程。", "Create the first SKILL.md to give agents a clear, auditable workflow.")}
          onRetry={() => void skills.refetch()}
        >
          {skills.data && <>
            <div className="table-scroll"><table className="data-table skills-table">
              <thead><tr><th>{text("技能", "Skill")}</th><th>{text("所需能力", "Required capability")}</th><th>{text("发给谁", "Audience")}</th><th>{text("种类", "Kind")}</th><th>{text("版本", "Version")}</th><th>{text("状态", "Status")}</th><th><span className="sr-only">{text("操作", "Actions")}</span></th></tr></thead>
              <tbody>{skills.data.data.map((skill) => <tr key={skill.id}>
                <td><strong>{skill.title || skill.name}</strong><small className="mono-cell">{skill.name}</small>{skill.description && <small className="skill-description">{skill.description}</small>}</td>
                <td className="mono-cell">{skill.required_capability || <span className="muted-value">{text("全员", "Everyone")}</span>}</td>
                <td>{audienceLabel(skill, text)}</td>
                <td><span className={`kind-chip ${skill.kind}`}>{skill.kind === "product" ? text("产品", "Product") : text("自定义", "Custom")}</span></td>
                <td><span className="version-chip">v{skill.version}</span></td>
                <td><StatusBadge status={skill.status} /></td>
                <td className="row-actions">
                  <button className="text-action" type="button" disabled={loadingName === skill.name} onClick={() => { const requestId = ++editRequestId.current; loadSkill.mutate({ name: skill.name, requestId }); }}>{loadingName === skill.name ? text("载入中…", "Loading…") : text("编辑", "Edit")}</button>
                  <button className={`text-action ${skill.status === "active" ? "danger-text" : ""}`} type="button" disabled={toggle.isPending} onClick={() => toggle.mutate(skill)}>{skill.status === "active" ? text("归档", "Archive") : text("恢复", "Restore")}</button>
                </td>
              </tr>)}</tbody>
            </table></div>
            <Pagination meta={skills.data.meta} onPageChange={setPage} />
          </>}
        </ListState>
      </section>

      <Drawer
        open={editing !== undefined}
        title={editing ? text("编辑技能", "Edit skill") : text("新建技能", "New skill")}
        description={editing ? text(`${editing.name} · v${editing.version}${editing.kind === "product" ? " · 保存后创建自定义版本" : ""}`, `${editing.name} · v${editing.version}${editing.kind === "product" ? " · saving creates a custom version" : ""}`) : text("技能是随工作空间分发给 AI 代理、并保留版本记录的文件包。", "A skill is a versioned file bundle distributed to AI agents for this workspace.")}
        submitLabel={editing ? text("保存技能", "Save skill") : text("创建技能", "Create skill")}
        busy={save.isPending}
        submitDisabled={!catalogReady}
        error={validation || (save.isError ? apiErrorMessage(save.error) : null)}
        onClose={() => { if (!save.isPending) { editRequestId.current += 1; setLoadingName(null); setEditing(undefined); } }}
        onSubmit={submit}
      >
        <div className="field-grid skill-fields">
          <div className="field"><label htmlFor="skill-name">{text("名称", "Name")} <b>*</b></label><input id="skill-name" required disabled={Boolean(editing)} maxLength={100} placeholder="daily-report-submit" value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} /></div>
          <div className="field"><label htmlFor="skill-title">{text("显示标题", "Display title")}</label><input id="skill-title" maxLength={200} value={draft.title} onChange={(e) => setDraft({ ...draft, title: e.target.value })} /></div>
          <div className="field span-2"><label htmlFor="skill-description">{text("触发描述", "Trigger description")}</label><textarea id="skill-description" rows={3} maxLength={2000} value={draft.description} onChange={(e) => setDraft({ ...draft, description: e.target.value })} /></div>
          <div className="field span-2"><label htmlFor="skill-capability">{text("所需能力", "Required capability")}</label><select id="skill-capability" disabled={!catalogReady} value={capabilitySelectValue} onChange={(e) => { setCapabilitySelectionTouched(true); setDraft({ ...draft, requiredCapability: e.target.value }); }}><option value="">{text("无（所有人可见）", "None (visible to everyone)")}</option>{!capabilityStillKnown && <option value={capabilitySelectValue}>{text(`${capabilitySelectValue}（目录中已不存在）`, `${capabilitySelectValue} (no longer in catalog)`)}</option>}{grouped.map((group) => { const options = capabilityOptions.filter((option) => option.group === group); return options.length ? <optgroup key={group} label={group}>{options.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</optgroup> : null; })}</select>{catalog.isPending && <small>{text("正在加载能力目录，加载完成前不能保存。", "Loading capability catalog; saving is disabled until it is ready.")}</small>}{catalog.isError && <small className="field-error" role="alert">{text("能力目录加载失败。", "Capability catalog could not be loaded.")}<button className="inline-retry" type="button" onClick={() => void catalog.refetch()}>{text("重试", "Retry")}</button></small>}{!draft.requiredCapability && !capabilitySelectionTouched && frontmatterCapability && <small>{text("已从 SKILL.md frontmatter 读取；选择“无”可明确设为全员可见。", "Read from SKILL.md frontmatter; select “None” to make the skill explicitly visible to everyone.")}</small>}{!draft.requiredCapability && capabilitySelectionTouched && frontmatterCapability && <small>{text(`已明确忽略 SKILL.md 中的 ${frontmatterCapability}，保存后将对所有人可见。`, `${frontmatterCapability} from SKILL.md is explicitly ignored; after saving, the skill will be visible to everyone.`)}</small>}<small>{text("需要新增对象作用域或自定义能力？前往", "Need a new object scope or custom capability? Go to")} <Link to="/object-types">{text("对象类型", "Object types")}</Link> {text("或", "or")} <Link to="/roles">{text("角色与权限", "Roles & permissions")}</Link>.</small></div>
        </div>

        {editing && <SkillAudiencePanel skillName={editing.name} />}

        <section className="skill-file-editor">
          <header><div><strong>{text("技能文件", "Skill files")}</strong><small>{text("必须包含 SKILL.md，最多 32 个文件。", "Must include SKILL.md; up to 32 files.")}</small></div><button className="button compact" type="button" disabled={draft.files.length >= 32} onClick={() => setDraft({ ...draft, files: [...draft.files, file("", "")] })}>{text("添加文件", "Add file")}</button></header>
          {draft.files.map((item) => <article className="skill-file" key={item.id}>
            <div><label htmlFor={`skill-path-${item.id}`}>{text("相对路径", "Relative path")}</label><input id={`skill-path-${item.id}`} value={item.path} onChange={(e) => changeFile(item.id, "path", e.target.value)} /><button className="text-action danger-text" type="button" disabled={draft.files.length === 1} onClick={() => setDraft({ ...draft, files: draft.files.filter((candidate) => candidate.id !== item.id) })}>{text("移除", "Remove")}</button></div>
            <textarea aria-label={text(`${item.path || "新文件"} 内容`, `${item.path || "New file"} content`)} className="code-editor" rows={item.path === "SKILL.md" ? 15 : 8} value={item.content} onChange={(e) => changeFile(item.id, "content", e.target.value)} />
          </article>)}
        </section>
      </Drawer>
    </div>
  );
}
