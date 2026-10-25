import { zhCN } from "../locales/zh-CN/console";
import { useRecordNotice } from "../components/master-data/RecordNotice";
import { useListFilters } from "../components/master-data/useListFilters";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import {
  archiveProject,
  createProject,
  listCustomers,
  listEmployees,
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
  // where the project came from: the customer it is for and who owns it
  // (plan 2026-10-14); the deal and the contract are set by the won-deal
  // bridge and the contract desk, and shown here read-only
  customerId: string;
  ownerEmployeeId: string;
  startDate: string;
  endDate: string;
  status: Exclude<StatusFilter, "">;
};

const emptyForm: ProjectForm = {
  name: "",
  code: "",
  client: "",
  customerId: "",
  ownerEmployeeId: "",
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
    customerId: project.customer_id ?? "",
    ownerEmployeeId: project.owner_employee_id ?? "",
    startDate: project.start_date ?? "",
    endDate: project.end_date ?? "",
    status: project.status,
  };
}

export function ProjectsPage() {
  const { text } = useI18n();
  const queryClient = useQueryClient();
  const { notice, notify } = useRecordNotice();
  const { keyword, status, page, setPage, applyFilters } = useListFilters<StatusFilter>(["active", "archived"]);
  const [editing, setEditing] = useState<Project | null | undefined>(undefined);
  const [archiving, setArchiving] = useState<Project | null>(null);
  const [form, setForm] = useState<ProjectForm>(emptyForm);
  const drawerOpen = editing !== undefined;
  const customers = useQuery({
    queryKey: ["customers", "picker"],
    queryFn: () => listCustomers({ size: 200, status: "active" }),
    enabled: drawerOpen,
  });
  const employees = useQuery({
    queryKey: ["employees", "picker"],
    queryFn: () => listEmployees({ size: 200, status: "active" }),
    enabled: drawerOpen,
  });
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
      notify(variables.id ? "saved" : "created");
      if (!variables.id) setPage(1);
      await queryClient.invalidateQueries({ queryKey: ["master-data", "projects"] });
    },
  });

  const archive = useMutation({
    mutationFn: (id: string) => archiveProject(id),
    onSuccess: async () => {
      setArchiving(null);
      notify("archived");
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
      setValidationError(text(zhCN.pagesProjectsPage.projectNameIsRequired, "Project name is required."));
      return;
    }
    if (form.startDate && form.endDate && form.endDate < form.startDate) {
      setValidationError(text(zhCN.pagesProjectsPage.endDateCannotBeEarlierThanTheStartDate, "End date cannot be earlier than the start date."));
      return;
    }
    setValidationError(null);
    save.mutate({
      id: editing?.id,
      input: {
        project_name: name,
        project_code: form.code.trim() || null,
        client: form.client.trim() || null,
        customer_id: form.customerId || null,
        owner_employee_id: form.ownerEmployeeId || null,
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
          <h2>{text(zhCN.pagesProjectsPage.projects, "Projects")}</h2>
          <p>{text(zhCN.pagesProjectsPage.maintainProjectCodesCustomersAndActiveDatesForTimesheets, "Maintain project codes, customers, and active dates for timesheets, expenses, and agent workflows.")}</p>
        </div>
      </header>
      {notice}

      <section className="data-panel" aria-label={text(zhCN.pagesProjectsPage.projectList, "Project list")}>
        <ListToolbar
          keyword={keyword}
          status={status}
          placeholder={text(zhCN.pagesProjectsPage.searchProjectNames, "Search project names")}
          createLabel={text(zhCN.pagesProjectsPage.newProject, "New project")}
          statusOptions={[{ value: "active", label: text(zhCN.pagesProjectsPage.active, "Active") }, { value: "archived", label: text(zhCN.pagesProjectsPage.archived, "Archived") }]}
          onCreate={openCreate}
          onApply={applyFilters}
        />
        <ListState
          loading={projects.isPending}
          error={projects.isError ? apiErrorMessage(projects.error) : null}
          empty={Boolean(result && result.data.length === 0)}
          emptyTitle={keyword || status ? text(zhCN.pagesProjectsPage.noMatchingProjects, "No matching projects") : text(zhCN.pagesProjectsPage.noProjectsYet, "No projects yet")}
          emptyDescription={keyword || status ? text(zhCN.pagesProjectsPage.tryChangingYourSearchOrStatusFilter, "Try changing your search or status filter.") : text(zhCN.pagesProjectsPage.createYourFirstProjectToGiveBusinessRecordsA, "Create your first project to give business records a clear home.")}
          onRetry={() => void projects.refetch()}
        >
          {result && (
            <>
              <div className="table-scroll">
                <table className="data-table">
                  <thead><tr><th>{text(zhCN.pagesProjectsPage.project, "Project")}</th><th>{text(zhCN.pagesProjectsPage.customer, "Customer")}</th><th>{text(zhCN.pagesProjectsPage.activePeriod, "Active period")}</th><th>{text(zhCN.pagesProjectsPage.status, "Status")}</th><th><span className="sr-only">{text(zhCN.pagesProjectsPage.actions, "Actions")}</span></th></tr></thead>
                  <tbody>
                    {result.data.map((project) => (
                      <tr key={project.id}>
                        <td><button className="record-name" type="button" onClick={() => openEdit(project)}>{project.project_name}</button><small>{project.project_code || text(zhCN.pagesProjectsPage.noCode, "No code")}</small></td>
                        <td>{project.client || <span className="muted-value">—</span>}</td>
                        <td>{project.start_date || project.end_date ? `${project.start_date || "…"} → ${project.end_date || "…"}` : <span className="muted-value">{text(zhCN.pagesProjectsPage.ongoing, "Ongoing")}</span>}</td>
                        <td><StatusBadge status={project.status} /></td>
                        <td className="row-actions">
                          <button className="text-action" type="button" onClick={() => openEdit(project)}>{text(zhCN.pagesProjectsPage.edit, "Edit")}</button>
                          {project.status !== "archived" && <button className="text-action danger-text" type="button" onClick={() => { archive.reset(); setArchiving(project); }}>{text(zhCN.pagesProjectsPage.archive, "Archive")}</button>}
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
        title={editing ? text(zhCN.pagesProjectsPage.editProject, "Edit project") : text(zhCN.pagesProjectsPage.newProject, "New project")}
        description={editing ? text(zhCN.pagesProjectsPage.updateMasterDataFor(`${editing.project_name}`), `Update master data for ${editing.project_name}.`) : text(zhCN.pagesProjectsPage.createAProjectThatBusinessRecordsCanReference, "Create a project that business records can reference.")}
        submitLabel={editing ? text(zhCN.pagesProjectsPage.saveChanges, "Save changes") : text(zhCN.pagesProjectsPage.createProject, "Create project")}
        busy={save.isPending}
        error={validationError || (save.isError ? apiErrorMessage(save.error) : null)}
        onClose={closeDrawer}
        onSubmit={submit}
      >
        <div className="field-grid">
          <div className="field span-2"><label htmlFor="project-name">{text(zhCN.pagesProjectsPage.projectName, "Project name")} <b>*</b></label><input id="project-name" required maxLength={200} value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} /></div>
          <div className="field"><label htmlFor="project-code">{text(zhCN.pagesProjectsPage.projectCode, "Project code")}</label><input id="project-code" maxLength={64} value={form.code} onChange={(event) => setForm({ ...form, code: event.target.value })} /></div>
          <div className="field"><label htmlFor="project-status">{text(zhCN.pagesProjectsPage.status, "Status")}</label><select id="project-status" value={form.status} onChange={(event) => setForm({ ...form, status: event.target.value as ProjectForm["status"] })}><option value="active">{text(zhCN.pagesProjectsPage.active, "Active")}</option><option value="archived">{text(zhCN.pagesProjectsPage.archived, "Archived")}</option></select></div>
          <div className="field"><label htmlFor="project-customer">{text(zhCN.pagesProjectsPage.customer, "Customer")}</label><select id="project-customer" value={form.customerId} onChange={(event) => setForm({ ...form, customerId: event.target.value })}><option value="">{text(zhCN.pagesProjectsPage.notLinked, "Not linked")}</option>{(customers.data?.data ?? []).map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select><small>{text(zhCN.pagesProjectsPage.linkedTheProjectReachesItsQuotationsContractAndInvoices, "Linked, the project reaches its quotations, contract and invoices; unlinked, the name below is only text.")}</small></div>
          <div className="field"><label htmlFor="project-owner">{text(zhCN.pagesProjectsPage.owner, "Owner")}</label><select id="project-owner" value={form.ownerEmployeeId} onChange={(event) => setForm({ ...form, ownerEmployeeId: event.target.value })}><option value="">{text(zhCN.pagesProjectsPage.unassigned, "Unassigned")}</option>{(employees.data?.data ?? []).map((e) => <option key={e.id} value={e.id}>{e.name}</option>)}</select></div>
          <div className="field span-2"><label htmlFor="project-client">{text(zhCN.pagesProjectsPage.customerNameText, "Customer name (text)")}</label><input id="project-client" maxLength={200} value={form.client} onChange={(event) => setForm({ ...form, client: event.target.value })} placeholder={form.customerId ? text(zhCN.pagesProjectsPage.emptyTakesTheCustomerSName, "Empty takes the customer's name") : undefined} /></div>
          {editing && (editing.opportunity_id || editing.contract_id) && <small className="span-2">{text(zhCN.pagesProjectsPage.fromADealContractSetByTheWonDeal(`${editing.opportunity_id ? "✓" : "—"}`, `${editing.contract_id ? "✓" : "—"}`), `From a deal ${editing.opportunity_id ? "✓" : "—"} · contract ${editing.contract_id ? "✓" : "—"} (set by the won-deal bridge and the contract desk)`)}</small>}
          <div className="field"><label htmlFor="project-start">{text(zhCN.pagesProjectsPage.startDate, "Start date")}</label><input id="project-start" type="date" value={form.startDate} onChange={(event) => setForm({ ...form, startDate: event.target.value })} /></div>
          <div className="field"><label htmlFor="project-end">{text(zhCN.pagesProjectsPage.endDate, "End date")}</label><input id="project-end" type="date" value={form.endDate} min={form.startDate || undefined} onChange={(event) => setForm({ ...form, endDate: event.target.value })} /></div>
        </div>
      </Drawer>

      <ConfirmDialog
        open={Boolean(archiving)}
        title={text(zhCN.pagesProjectsPage.archive2(`${archiving?.project_name ?? ""}`), `Archive “${archiving?.project_name ?? ""}”?`)}
        description={text(zhCN.pagesProjectsPage.archivingKeepsHistoricalReferencesButThisProjectWillNo, "Archiving keeps historical references, but this project will no longer be available as active.")}
        busy={archive.isPending}
        error={archive.isError ? apiErrorMessage(archive.error) : null}
        onCancel={() => !archive.isPending && setArchiving(null)}
        onConfirm={() => archiving && archive.mutate(archiving.id)}
      />
    </div>
  );
}
