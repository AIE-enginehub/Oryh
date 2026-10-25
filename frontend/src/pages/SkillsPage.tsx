import { zhCN } from "../locales/zh-CN/console";
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
const ZH_SKILL_TEMPLATE = zhCN.pagesSkillsPage.message;
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

function blankSkill(template: string = ZH_SKILL_TEMPLATE): SkillForm {
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
    return <span className="muted-value">{text(zhCN.pagesSkillsPage.byCapability, "By capability")}</span>;
  }
  const roles = skill.audience?.roles ?? [];
  const people = skill.audience?.user_count ?? 0;
  if (roles.length === 0 && people === 0) {
    // the runner ignores audience, so a flow skill with nobody named is
    // exactly as shipped; name a person only to let them take over by hand
    return skill.runs_unattended
      ? <span className="muted-value">{text(zhCN.pagesSkillsPage.runnerOnly, "Runner only")}</span>
      : <span className="audience-empty">{text(zhCN.pagesSkillsPage.targetedNobody, "Targeted · nobody")}</span>;
  }
  const parts = [...roles];
  if (people > 0) parts.push(text(zhCN.pagesSkillsPage.template(`${people}`), `${people} ${people === 1 ? "person" : "people"}`));
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
        values.push({ value: capability.name, label: capability.title ? `${capability.name} — ${capability.title}` : capability.name, group: text(zhCN.pagesSkillsPage.customCapabilities, "Custom capabilities") });
      } else if (capability.scopable) {
        values.push({ value: `${capability.name}:*`, label: zhCN.pagesSkillsPage.label(`${capability.name}`, `${text(zhCN.pagesSkillsPage.allObjectTypes, "All object types")}`), group: text(zhCN.pagesSkillsPage.scopedCapabilities, "Scoped capabilities") });
        for (const objectType of catalog.data.object_types) {
          values.push({ value: `${capability.name}:${objectType}`, label: `${capability.name}:${objectType}`, group: text(zhCN.pagesSkillsPage.scopedCapabilities, "Scoped capabilities") });
        }
      } else {
        values.push({ value: capability.name, label: capability.title ? `${capability.name} — ${capability.title}` : capability.name, group: text(zhCN.pagesSkillsPage.systemCapabilities, "System capabilities") });
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
      setValidation(text(zhCN.pagesSkillsPage.theCapabilityCatalogIsNotReadyRetryBeforeSaving, "The capability catalog is not ready. Retry before saving to avoid changing the skill's distribution unexpectedly."));
      return;
    }
    const name = draft.name.trim();
    if (!editing && !NAME_PATTERN.test(name)) {
      setValidation(text(zhCN.pagesSkillsPage.namesMayContainOnlyLowercaseLettersNumbersAndSingle, "Names may contain only lowercase letters, numbers, and single hyphens, for example daily-report-submit."));
      return;
    }
    const paths = draft.files.map((item) => item.path.trim());
    if (paths.some((path) => !path)) {
      setValidation(text(zhCN.pagesSkillsPage.everySkillFileMustHaveARelativePath, "Every skill file must have a relative path."));
      return;
    }
    if (new Set(paths).size !== paths.length) {
      setValidation(text(zhCN.pagesSkillsPage.skillFilePathsMustBeUnique, "Skill file paths must be unique."));
      return;
    }
    if (!paths.includes("SKILL.md")) {
      setValidation(text(zhCN.pagesSkillsPage.skillFilesMustIncludeSKILLMd, "Skill files must include SKILL.md."));
      return;
    }
    if (paths.some((path) => path.startsWith("/") || path.includes("..") || path.includes("\\"))) {
      setValidation(text(zhCN.pagesSkillsPage.filesMustUseSafeRelativePathsAndCannotStart, "Files must use safe relative paths and cannot start with / or contain .. or backslashes."));
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

  const grouped = [text(zhCN.pagesSkillsPage.systemCapabilities, "System capabilities"), text(zhCN.pagesSkillsPage.scopedCapabilities, "Scoped capabilities"), text(zhCN.pagesSkillsPage.customCapabilities, "Custom capabilities")];
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
          <span className="eyebrow">{text(zhCN.pagesSkillsPage.agentContracts, "Agent contracts")}</span>
          <h2>{text(zhCN.pagesSkillsPage.skills, "Skills")}</h2>
          <p>{text(zhCN.pagesSkillsPage.manageAIAgentWorkflowInstructionsTriggerDescriptionsFilesAnd, "Manage AI agent workflow instructions, trigger descriptions, files, and role-based distribution for this workspace.")}</p>
        </div>
        <button className="button primary" type="button" onClick={openCreate}>{text(zhCN.pagesSkillsPage.newSkill, "New skill")}</button>
      </header>

      <aside className="info-banner">
        <strong>{text(zhCN.pagesSkillsPage.distributionAndAuthorizationAreIndependent, "Distribution and authorization are independent.")}</strong>
        <span>{text(zhCN.pagesSkillsPage.theRequiredPermissionDeterminesWhichRolesReceiveASkill, "The required permission determines which roles receive a skill; Oryh checks every action against the same permission.")}</span>
      </aside>

      {((loadSkill.isError && loadSkill.variables?.requestId === editRequestId.current) || toggle.isError) && <div className="form-error" role="alert">{apiErrorMessage(loadSkill.isError && loadSkill.variables?.requestId === editRequestId.current ? loadSkill.error : toggle.error)}</div>}

      <section className="data-panel" aria-label={text(zhCN.pagesSkillsPage.skillList, "Skill list")}>
        <header className="section-bar">
          <div><strong>{text(zhCN.pagesSkillsPage.skillCatalog, "Skill catalog")}</strong><small>{text(zhCN.pagesSkillsPage.productSkillsCanBeSavedAsWorkspaceSpecificVersions, "Product skills can be saved as workspace-specific versions with full version history.")}</small></div>
          <form className="compact-filters" onSubmit={(e) => { e.preventDefault(); setKeyword(keywordDraft.trim()); setPage(1); }}>
            <input aria-label={text(zhCN.pagesSkillsPage.searchSkills, "Search skills")} placeholder={text(zhCN.pagesSkillsPage.searchNameOrDescription, "Search name or description")} value={keywordDraft} onChange={(e) => setKeywordDraft(e.target.value)} />
            <select aria-label={text(zhCN.pagesSkillsPage.skillStatus, "Skill status")} value={status} onChange={(e) => { setStatus(e.target.value as SkillStatus | "all"); setPage(1); }}><option value="all">{text(zhCN.pagesSkillsPage.allStatuses, "All statuses")}</option><option value="active">{text(zhCN.pagesSkillsPage.active, "Active")}</option><option value="archived">{text(zhCN.pagesSkillsPage.archived, "Archived")}</option></select>
            <button className="button compact" type="submit">{text(zhCN.pagesSkillsPage.filter, "Filter")}</button>
          </form>
        </header>
        <ListState
          loading={skills.isPending}
          error={skills.isError ? apiErrorMessage(skills.error) : null}
          empty={Boolean(skills.data && skills.data.data.length === 0)}
          emptyTitle={text(zhCN.pagesSkillsPage.noSkillsYet, "No skills yet")}
          emptyDescription={text(zhCN.pagesSkillsPage.createTheFirstSKILLMdToGiveAgentsA, "Create the first SKILL.md to give agents a clear, auditable workflow.")}
          onRetry={() => void skills.refetch()}
        >
          {skills.data && <>
            <div className="table-scroll"><table className="data-table skills-table">
              <thead><tr><th>{text(zhCN.pagesSkillsPage.skills, "Skill")}</th><th>{text(zhCN.pagesSkillsPage.requiredCapability, "Required capability")}</th><th>{text(zhCN.pagesSkillsPage.audience, "Audience")}</th><th>{text(zhCN.pagesSkillsPage.kind, "Kind")}</th><th>{text(zhCN.pagesSkillsPage.version, "Version")}</th><th>{text(zhCN.pagesSkillsPage.status, "Status")}</th><th><span className="sr-only">{text(zhCN.pagesSkillsPage.actions, "Actions")}</span></th></tr></thead>
              <tbody>{skills.data.data.map((skill) => <tr key={skill.id}>
                <td><strong>{skill.title || skill.name}</strong><small className="mono-cell">{skill.name}</small>{skill.description && <small className="skill-description">{skill.description}</small>}</td>
                <td className="mono-cell">{skill.required_capability || <span className="muted-value">{text(zhCN.pagesSkillsPage.everyone, "Everyone")}</span>}</td>
                <td>{audienceLabel(skill, text)}</td>
                <td><span className={`kind-chip ${skill.kind}`}>{skill.kind === "product" ? text(zhCN.pagesSkillsPage.product, "Product") : text(zhCN.pagesSkillsPage.custom, "Custom")}</span></td>
                <td><span className="version-chip">v{skill.version}</span></td>
                <td><StatusBadge status={skill.status} /></td>
                <td className="row-actions">
                  <button className="text-action" type="button" disabled={loadingName === skill.name} onClick={() => { const requestId = ++editRequestId.current; loadSkill.mutate({ name: skill.name, requestId }); }}>{loadingName === skill.name ? text(zhCN.pagesSkillsPage.loading, "Loading…") : text(zhCN.pagesSkillsPage.edit, "Edit")}</button>
                  <button className={`text-action ${skill.status === "active" ? "danger-text" : ""}`} type="button" disabled={toggle.isPending} onClick={() => toggle.mutate(skill)}>{skill.status === "active" ? text(zhCN.pagesSkillsPage.archive, "Archive") : text(zhCN.pagesSkillsPage.restore, "Restore")}</button>
                </td>
              </tr>)}</tbody>
            </table></div>
            <Pagination meta={skills.data.meta} onPageChange={setPage} />
          </>}
        </ListState>
      </section>

      <Drawer
        open={editing !== undefined}
        title={editing ? text(zhCN.pagesSkillsPage.editSkill, "Edit skill") : text(zhCN.pagesSkillsPage.newSkill, "New skill")}
        description={editing ? text(zhCN.pagesSkillsPage.v(`${editing.name}`, `${editing.version}`, `${editing.kind === "product" ? zhCN.pagesSkillsPage.message2 : ""}`), `${editing.name} · v${editing.version}${editing.kind === "product" ? " · saving creates a custom version" : ""}`) : text(zhCN.pagesSkillsPage.aSkillIsAVersionedFileBundleDistributedTo, "A skill is a versioned file bundle distributed to AI agents for this workspace.")}
        submitLabel={editing ? text(zhCN.pagesSkillsPage.saveSkill, "Save skill") : text(zhCN.pagesSkillsPage.createSkill, "Create skill")}
        busy={save.isPending}
        submitDisabled={!catalogReady}
        error={validation || (save.isError ? apiErrorMessage(save.error) : null)}
        onClose={() => { if (!save.isPending) { editRequestId.current += 1; setLoadingName(null); setEditing(undefined); } }}
        onSubmit={submit}
      >
        <div className="field-grid skill-fields">
          <div className="field"><label htmlFor="skill-name">{text(zhCN.pagesSkillsPage.name, "Name")} <b>*</b></label><input id="skill-name" required disabled={Boolean(editing)} maxLength={100} placeholder="daily-report-submit" value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} /></div>
          <div className="field"><label htmlFor="skill-title">{text(zhCN.pagesSkillsPage.displayTitle, "Display title")}</label><input id="skill-title" maxLength={200} value={draft.title} onChange={(e) => setDraft({ ...draft, title: e.target.value })} /></div>
          <div className="field span-2"><label htmlFor="skill-description">{text(zhCN.pagesSkillsPage.triggerDescription, "Trigger description")}</label><textarea id="skill-description" rows={3} maxLength={2000} value={draft.description} onChange={(e) => setDraft({ ...draft, description: e.target.value })} /></div>
          <div className="field span-2"><label htmlFor="skill-capability">{text(zhCN.pagesSkillsPage.requiredCapability, "Required capability")}</label><select id="skill-capability" disabled={!catalogReady} value={capabilitySelectValue} onChange={(e) => { setCapabilitySelectionTouched(true); setDraft({ ...draft, requiredCapability: e.target.value }); }}><option value="">{text(zhCN.pagesSkillsPage.noneVisibleToEveryone, "None (visible to everyone)")}</option>{!capabilityStillKnown && <option value={capabilitySelectValue}>{text(zhCN.pagesSkillsPage.noLongerInCatalog(`${capabilitySelectValue}`), `${capabilitySelectValue} (no longer in catalog)`)}</option>}{grouped.map((group) => { const options = capabilityOptions.filter((option) => option.group === group); return options.length ? <optgroup key={group} label={group}>{options.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</optgroup> : null; })}</select>{catalog.isPending && <small>{text(zhCN.pagesSkillsPage.loadingCapabilityCatalogSavingIsDisabledUntilItIs, "Loading capability catalog; saving is disabled until it is ready.")}</small>}{catalog.isError && <small className="field-error" role="alert">{text(zhCN.pagesSkillsPage.capabilityCatalogCouldNotBeLoaded, "Capability catalog could not be loaded.")}<button className="inline-retry" type="button" onClick={() => void catalog.refetch()}>{text(zhCN.pagesSkillsPage.retry, "Retry")}</button></small>}{!draft.requiredCapability && !capabilitySelectionTouched && frontmatterCapability && <small>{text(zhCN.pagesSkillsPage.readFromSKILLMdFrontmatterSelectNoneToMake, "Read from SKILL.md frontmatter; select “None” to make the skill explicitly visible to everyone.")}</small>}{!draft.requiredCapability && capabilitySelectionTouched && frontmatterCapability && <small>{text(zhCN.pagesSkillsPage.fromSKILLMdIsExplicitlyIgnoredAfterSavingThe(`${frontmatterCapability}`), `${frontmatterCapability} from SKILL.md is explicitly ignored; after saving, the skill will be visible to everyone.`)}</small>}<small>{text(zhCN.pagesSkillsPage.needANewObjectScopeOrCustomCapabilityGo, "Need a new object scope or custom capability? Go to")} <Link to="/object-types">{text(zhCN.pagesSkillsPage.objectTypes, "Object types")}</Link> {text(zhCN.pagesSkillsPage.or, "or")} <Link to="/roles">{text(zhCN.pagesSkillsPage.rolesPermissions, "Roles & permissions")}</Link>.</small></div>
        </div>

        {editing && <SkillAudiencePanel skillName={editing.name} />}

        <section className="skill-file-editor">
          <header><div><strong>{text(zhCN.pagesSkillsPage.skillFiles, "Skill files")}</strong><small>{text(zhCN.pagesSkillsPage.mustIncludeSKILLMdUpTo32Files, "Must include SKILL.md; up to 32 files.")}</small></div><button className="button compact" type="button" disabled={draft.files.length >= 32} onClick={() => setDraft({ ...draft, files: [...draft.files, file("", "")] })}>{text(zhCN.pagesSkillsPage.addFile, "Add file")}</button></header>
          {draft.files.map((item) => <article className="skill-file" key={item.id}>
            <div><label htmlFor={`skill-path-${item.id}`}>{text(zhCN.pagesSkillsPage.relativePath, "Relative path")}</label><input id={`skill-path-${item.id}`} value={item.path} onChange={(e) => changeFile(item.id, "path", e.target.value)} /><button className="text-action danger-text" type="button" disabled={draft.files.length === 1} onClick={() => setDraft({ ...draft, files: draft.files.filter((candidate) => candidate.id !== item.id) })}>{text(zhCN.pagesSkillsPage.remove, "Remove")}</button></div>
            <textarea aria-label={text(zhCN.pagesSkillsPage.content(`${item.path || zhCN.pagesSkillsPage.message3}`), `${item.path || "New file"} content`)} className="code-editor" rows={item.path === "SKILL.md" ? 15 : 8} value={item.content} onChange={(e) => changeFile(item.id, "content", e.target.value)} />
          </article>)}
        </section>
      </Drawer>
    </div>
  );
}
