import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import {
  archiveProject,
  createProject,
  listProjects,
  updateProject,
  type CreateProjectInput,
  type Project,
} from "../api/client";
import { ConfirmDialog } from "../components/master-data/ConfirmDialog";
import { Drawer } from "../components/master-data/Drawer";
import { apiErrorMessage, ListState, StatusBadge } from "../components/master-data/ListState";
import { ListToolbar } from "../components/master-data/ListToolbar";
import { Pagination } from "../components/master-data/Pagination";
import { useI18n } from "../i18n";

const PAGE_SIZE = 20;
type StatusFilter = "" | "active" | "archived";
type ProjectForm = {
  name: string;
  code: string;
  client: string;
  startDate: string;
  endDate: string;
  status: Exclude<StatusFilter, "">;
};

const emptyForm: ProjectForm = {
  name: "",
  code: "",
  client: "",
  startDate: "",
  endDate: "",
  status: "active",
};

function projectForm(project?: Project): ProjectForm {
  if (!project) return emptyForm;
  return {
    name: project.project_name,
    code: project.project_code ?? "",
    client: project.client ?? "",
    startDate: project.start_date ?? "",
    endDate: project.end_date ?? "",
    status: project.status,
  };
}

export function ProjectsPage() {
  const { text } = useI18n();
  const queryClient = useQueryClient();
  const [keyword, setKeyword] = useState("");
  const [status, setStatus] = useState<StatusFilter>("");
  const [page, setPage] = useState(1);
  const [editing, setEditing] = useState<Project | null | undefined>(undefined);
  const [archiving, setArchiving] = useState<Project | null>(null);
  const [form, setForm] = useState<ProjectForm>(emptyForm);
  const [validationError, setValidationError] = useState<string | null>(null);

  const projects = useQuery({
    queryKey: ["master-data", "projects", { keyword, status, page }],
    queryFn: () => listProjects({
      page,
      size: PAGE_SIZE,
      keyword: keyword || undefined,
      status: status || undefined,
    }),
    placeholderData: keepPreviousData,
  });

  const save = useMutation({
    mutationFn: ({ id, input }: { id?: string; input: CreateProjectInput }) =>
      id ? updateProject(id, input) : createProject(input),
    onSuccess: async (_project, variables) => {
      setEditing(undefined);
      if (!variables.id) setPage(1);
      await queryClient.invalidateQueries({ queryKey: ["master-data", "projects"] });
    },
  });

  const archive = useMutation({
    mutationFn: (id: string) => archiveProject(id),
    onSuccess: async () => {
      setArchiving(null);
      setPage(1);
      await queryClient.invalidateQueries({ queryKey: ["master-data", "projects"] });
    },
  });

  const openCreate = () => {
    setForm(emptyForm);
    setEditing(null);
    setValidationError(null);
    save.reset();
  };
  const openEdit = (project: Project) => {
    setForm(projectForm(project));
    setEditing(project);
    setValidationError(null);
    save.reset();
  };
  const closeDrawer = () => {
    if (!save.isPending) setEditing(undefined);
  };

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const name = form.name.trim();
    if (!name) {
      setValidationError(text("项目名称不能为空。", "Project name is required."));
      return;
    }
    if (form.startDate && form.endDate && form.endDate < form.startDate) {
      setValidationError(text("结束日期不能早于开始日期。", "End date cannot be earlier than the start date."));
      return;
    }
    setValidationError(null);
    save.mutate({
      id: editing?.id,
      input: {
        project_name: name,
        project_code: form.code.trim() || null,
        client: form.client.trim() || null,
        start_date: form.startDate || null,
        end_date: form.endDate || null,
        status: form.status,
      },
    });
  };

  const result = projects.data;
  return (
    <div className="master-data-page" data-testid="projects-page">
      <header className="page-intro">
        <div>
          <span className="eyebrow">Project registry</span>
          <h2>{text("项目主数据", "Project master data")}</h2>
          <p>{text("维护项目编号、客户和有效周期，供工时、费用与代理流程引用。", "Maintain project codes, customers, and active dates for timesheets, expenses, and agent workflows.")}</p>
        </div>
      </header>

      <section className="data-panel" aria-label={text("项目列表", "Project list")}>
        <ListToolbar
          keyword={keyword}
          status={status}
          placeholder={text("按项目名称搜索", "Search project names")}
          createLabel={text("新建项目", "New project")}
          statusOptions={[{ value: "active", label: text("启用", "Active") }, { value: "archived", label: text("已归档", "Archived") }]}
          onCreate={openCreate}
          onApply={(filters) => {
            setKeyword(filters.keyword);
            setStatus(filters.status as StatusFilter);
            setPage(1);
          }}
        />
        <ListState
          loading={projects.isPending}
          error={projects.isError ? apiErrorMessage(projects.error) : null}
          empty={Boolean(result && result.data.length === 0)}
          emptyTitle={keyword || status ? text("没有匹配的项目", "No matching projects") : text("还没有项目", "No projects yet")}
          emptyDescription={keyword || status ? text("尝试调整搜索词或状态筛选。", "Try changing your search or status filter.") : text("新建第一个项目，让业务记录有清晰归属。", "Create your first project to give business records a clear home.")}
          onRetry={() => void projects.refetch()}
        >
          {result && (
            <>
              <div className="table-scroll">
                <table className="data-table">
                  <thead><tr><th>{text("项目", "Project")}</th><th>{text("客户", "Customer")}</th><th>{text("有效期", "Active period")}</th><th>{text("状态", "Status")}</th><th><span className="sr-only">{text("操作", "Actions")}</span></th></tr></thead>
                  <tbody>
                    {result.data.map((project) => (
                      <tr key={project.id}>
                        <td><strong>{project.project_name}</strong><small>{project.project_code || text("未设置编号", "No code")}</small></td>
                        <td>{project.client || <span className="muted-value">—</span>}</td>
                        <td>{project.start_date || project.end_date ? `${project.start_date || "…"} → ${project.end_date || "…"}` : <span className="muted-value">{text("长期", "Ongoing")}</span>}</td>
                        <td><StatusBadge status={project.status} /></td>
                        <td className="row-actions">
                          <button className="text-action" type="button" onClick={() => openEdit(project)}>{text("编辑", "Edit")}</button>
                          {project.status !== "archived" && <button className="text-action danger-text" type="button" onClick={() => { archive.reset(); setArchiving(project); }}>{text("归档", "Archive")}</button>}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <Pagination meta={result.meta} onPageChange={setPage} />
            </>
          )}
        </ListState>
      </section>

      <Drawer
        open={editing !== undefined}
        title={editing ? text("编辑项目", "Edit project") : text("新建项目", "New project")}
        description={editing ? text(`更新 ${editing.project_name} 的主数据。`, `Update master data for ${editing.project_name}.`) : text("创建可供业务记录引用的项目。", "Create a project that business records can reference.")}
        submitLabel={editing ? text("保存更改", "Save changes") : text("创建项目", "Create project")}
        busy={save.isPending}
        error={validationError || (save.isError ? apiErrorMessage(save.error) : null)}
        onClose={closeDrawer}
        onSubmit={submit}
      >
        <div className="field-grid">
          <div className="field span-2"><label htmlFor="project-name">{text("项目名称", "Project name")} <b>*</b></label><input id="project-name" required maxLength={200} value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} /></div>
          <div className="field"><label htmlFor="project-code">{text("项目编号", "Project code")}</label><input id="project-code" maxLength={64} value={form.code} onChange={(event) => setForm({ ...form, code: event.target.value })} /></div>
          <div className="field"><label htmlFor="project-status">{text("状态", "Status")}</label><select id="project-status" value={form.status} onChange={(event) => setForm({ ...form, status: event.target.value as ProjectForm["status"] })}><option value="active">{text("启用", "Active")}</option><option value="archived">{text("已归档", "Archived")}</option></select></div>
          <div className="field span-2"><label htmlFor="project-client">{text("客户", "Customer")}</label><input id="project-client" maxLength={200} value={form.client} onChange={(event) => setForm({ ...form, client: event.target.value })} /></div>
          <div className="field"><label htmlFor="project-start">{text("开始日期", "Start date")}</label><input id="project-start" type="date" value={form.startDate} onChange={(event) => setForm({ ...form, startDate: event.target.value })} /></div>
          <div className="field"><label htmlFor="project-end">{text("结束日期", "End date")}</label><input id="project-end" type="date" value={form.endDate} min={form.startDate || undefined} onChange={(event) => setForm({ ...form, endDate: event.target.value })} /></div>
        </div>
      </Drawer>

      <ConfirmDialog
        open={Boolean(archiving)}
        title={text(`归档“${archiving?.project_name ?? ""}”？`, `Archive “${archiving?.project_name ?? ""}”?`)}
        description={text("归档后不会删除历史引用，但该项目将不再作为启用项使用。", "Archiving keeps historical references, but this project will no longer be available as active.")}
        busy={archive.isPending}
        error={archive.isError ? apiErrorMessage(archive.error) : null}
        onCancel={() => !archive.isPending && setArchiving(null)}
        onConfirm={() => archiving && archive.mutate(archiving.id)}
      />
    </div>
  );
}
