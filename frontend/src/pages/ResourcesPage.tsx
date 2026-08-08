import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import {
  archiveResource,
  createResource,
  listResources,
  updateResource,
  type CreateResourceInput,
  type Resource,
} from "../api/client";
import { ConfirmDialog } from "../components/master-data/ConfirmDialog";
import { Drawer } from "../components/master-data/Drawer";
import { apiErrorMessage, ListState, StatusBadge } from "../components/master-data/ListState";
import { ListToolbar } from "../components/master-data/ListToolbar";
import { Pagination } from "../components/master-data/Pagination";
import { useI18n } from "../i18n";

const PAGE_SIZE = 20;
type StatusFilter = "" | "active" | "inactive" | "archived";
type ResourceForm = {
  name: string;
  type: string;
  code: string;
  location: string;
  capacity: string;
  bookingMode: "exclusive" | "shared";
  maxQuantity: string;
  status: Exclude<StatusFilter, "">;
};

const emptyForm: ResourceForm = {
  name: "",
  type: "meeting_room",
  code: "",
  location: "",
  capacity: "",
  bookingMode: "exclusive",
  maxQuantity: "",
  status: "active",
};

function resourceForm(resource?: Resource): ResourceForm {
  if (!resource) return emptyForm;
  return {
    name: resource.name,
    type: resource.resource_type,
    code: resource.code ?? "",
    location: resource.location ?? "",
    capacity: resource.capacity?.toString() ?? "",
    bookingMode: resource.booking_mode,
    maxQuantity: resource.max_quantity?.toString() ?? "",
    status: resource.status,
  };
}

export function ResourcesPage() {
  const { text } = useI18n();
  const queryClient = useQueryClient();
  const [keyword, setKeyword] = useState("");
  const [status, setStatus] = useState<StatusFilter>("");
  const [page, setPage] = useState(1);
  const [editing, setEditing] = useState<Resource | null | undefined>(undefined);
  const [archiving, setArchiving] = useState<Resource | null>(null);
  const [form, setForm] = useState<ResourceForm>(emptyForm);
  const [validationError, setValidationError] = useState<string | null>(null);

  const resources = useQuery({
    queryKey: ["master-data", "resources", { keyword, status, page }],
    queryFn: () => listResources({ page, size: PAGE_SIZE, keyword: keyword || undefined, status: status || undefined }),
    placeholderData: keepPreviousData,
  });
  const save = useMutation({
    mutationFn: ({ id, input }: { id?: string; input: CreateResourceInput }) =>
      id ? updateResource(id, input) : createResource(input),
    onSuccess: async (_resource, variables) => {
      setEditing(undefined);
      if (!variables.id) setPage(1);
      await queryClient.invalidateQueries({ queryKey: ["master-data", "resources"] });
    },
  });
  const archive = useMutation({
    mutationFn: (id: string) => archiveResource(id),
    onSuccess: async () => {
      setArchiving(null);
      setPage(1);
      await queryClient.invalidateQueries({ queryKey: ["master-data", "resources"] });
    },
  });

  const openCreate = () => {
    setForm(emptyForm);
    setEditing(null);
    setValidationError(null);
    save.reset();
  };
  const openEdit = (resource: Resource) => {
    setForm(resourceForm(resource));
    setEditing(resource);
    setValidationError(null);
    save.reset();
  };
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!form.name.trim() || !form.type.trim()) {
      setValidationError(text("资源名称和资源类型不能为空。", "Resource name and type are required."));
      return;
    }
    const capacity = form.capacity ? Number(form.capacity) : null;
    const maxQuantity = form.maxQuantity ? Number(form.maxQuantity) : null;
    if (capacity !== null && (!Number.isInteger(capacity) || capacity < 1)) {
      setValidationError(text("容量必须是大于 0 的整数。", "Capacity must be a positive integer."));
      return;
    }
    if (form.bookingMode === "shared" && (maxQuantity === null || !Number.isInteger(maxQuantity) || maxQuantity < 1)) {
      setValidationError(text("共享资源必须设置大于 0 的最大可预订数量。", "Shared resources require a positive maximum bookable quantity."));
      return;
    }
    setValidationError(null);
    save.mutate({
      id: editing?.id,
      input: {
        name: form.name.trim(),
        resource_type: form.type.trim(),
        code: form.code.trim() || null,
        location: form.location.trim() || null,
        capacity,
        booking_mode: form.bookingMode,
        max_quantity: form.bookingMode === "shared" ? maxQuantity : null,
        status: form.status,
      },
    });
  };

  const result = resources.data;
  return (
    <div className="master-data-page" data-testid="resources-page">
      <header className="page-intro">
        <div><span className="eyebrow">Resource registry</span><h2>{text("资源主数据", "Resource master data")}</h2><p>{text("登记空间、设备和共享库存，并定义代理预订时使用的占用规则。", "Register spaces, equipment, and shared inventory, and define the capacity rules used for bookings.")}</p></div>
      </header>
      <section className="data-panel" aria-label={text("资源列表", "Resource list")}>
        <ListToolbar
          keyword={keyword}
          status={status}
          placeholder={text("按资源名称搜索", "Search resource names")}
          createLabel={text("新建资源", "New resource")}
          statusOptions={[{ value: "active", label: text("启用", "Active") }, { value: "inactive", label: text("停用", "Inactive") }, { value: "archived", label: text("已归档", "Archived") }]}
          onCreate={openCreate}
          onApply={(filters) => { setKeyword(filters.keyword); setStatus(filters.status as StatusFilter); setPage(1); }}
        />
        <ListState
          loading={resources.isPending}
          error={resources.isError ? apiErrorMessage(resources.error) : null}
          empty={Boolean(result && result.data.length === 0)}
          emptyTitle={keyword || status ? text("没有匹配的资源", "No matching resources") : text("还没有资源", "No resources yet")}
          emptyDescription={keyword || status ? text("尝试调整搜索词或状态筛选。", "Try changing your search or status filter.") : text("新建资源后，员工和代理可以按规则发起预订。", "Create a resource so employees and agents can book it according to its rules.")}
          onRetry={() => void resources.refetch()}
        >
          {result && <>
            <div className="table-scroll"><table className="data-table">
              <thead><tr><th>{text("资源", "Resource")}</th><th>{text("类型 / 位置", "Type / Location")}</th><th>{text("预订规则", "Booking rules")}</th><th>{text("状态", "Status")}</th><th><span className="sr-only">{text("操作", "Actions")}</span></th></tr></thead>
              <tbody>{result.data.map((resource) => (
                <tr key={resource.id}>
                  <td><strong>{resource.name}</strong><small>{resource.code || text("未设置编号", "No code")}</small></td>
                  <td><span>{resource.resource_type}</span><small>{resource.location || text("未设置位置", "No location")}{resource.capacity ? text(` · 容量 ${resource.capacity}`, ` · Capacity ${resource.capacity}`) : ""}</small></td>
                  <td>{resource.booking_mode === "shared" ? <><span>{text("共享数量", "Shared quantity")}</span><small>{text(`最多 ${resource.max_quantity ?? "—"}`, `Up to ${resource.max_quantity ?? "—"}`)}</small></> : <><span>{text("独占预订", "Exclusive booking")}</span><small>{text("同一时段仅一笔", "One booking per time slot")}</small></>}</td>
                  <td><StatusBadge status={resource.status} /></td>
                  <td className="row-actions"><button className="text-action" type="button" onClick={() => openEdit(resource)}>{text("编辑", "Edit")}</button>{resource.status !== "archived" && <button className="text-action danger-text" type="button" onClick={() => { archive.reset(); setArchiving(resource); }}>{text("归档", "Archive")}</button>}</td>
                </tr>
              ))}</tbody>
            </table></div>
            <Pagination meta={result.meta} onPageChange={setPage} />
          </>}
        </ListState>
      </section>

      <Drawer
        open={editing !== undefined}
        title={editing ? text("编辑资源", "Edit resource") : text("新建资源", "New resource")}
        description={editing ? text(`更新 ${editing.name} 的预订主数据。`, `Update booking master data for ${editing.name}.`) : text("登记可供员工或代理预订的资源。", "Register a resource that employees or agents can book.")}
        submitLabel={editing ? text("保存更改", "Save changes") : text("创建资源", "Create resource")}
        busy={save.isPending}
        error={validationError || (save.isError ? apiErrorMessage(save.error) : null)}
        onClose={() => !save.isPending && setEditing(undefined)}
        onSubmit={submit}
      >
        <div className="field-grid">
          <div className="field span-2"><label htmlFor="resource-name">{text("资源名称", "Resource name")} <b>*</b></label><input id="resource-name" required maxLength={200} value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} /></div>
          <div className="field"><label htmlFor="resource-type">{text("资源类型", "Resource type")} <b>*</b></label><input id="resource-type" required maxLength={100} list="resource-types" value={form.type} onChange={(event) => setForm({ ...form, type: event.target.value })} /><datalist id="resource-types"><option value="meeting_room" /><option value="vehicle" /><option value="equipment" /><option value="inventory" /></datalist></div>
          <div className="field"><label htmlFor="resource-code">{text("资源编号", "Resource code")}</label><input id="resource-code" maxLength={64} value={form.code} onChange={(event) => setForm({ ...form, code: event.target.value })} /></div>
          <div className="field span-2"><label htmlFor="resource-location">{text("位置", "Location")}</label><input id="resource-location" maxLength={200} value={form.location} onChange={(event) => setForm({ ...form, location: event.target.value })} /></div>
          <div className="field"><label htmlFor="resource-capacity">{text("容纳人数 / 容量", "Occupancy / Capacity")}</label><input id="resource-capacity" type="number" min="1" step="1" value={form.capacity} onChange={(event) => setForm({ ...form, capacity: event.target.value })} /></div>
          <div className="field"><label htmlFor="resource-status">{text("状态", "Status")}</label><select id="resource-status" value={form.status} onChange={(event) => setForm({ ...form, status: event.target.value as ResourceForm["status"] })}><option value="active">{text("启用", "Active")}</option><option value="inactive">{text("停用", "Inactive")}</option><option value="archived">{text("已归档", "Archived")}</option></select></div>
          <fieldset className="field span-2 booking-field"><legend>{text("预订模式", "Booking mode")}</legend><div className="segmented-control"><label><input type="radio" name="booking-mode" value="exclusive" checked={form.bookingMode === "exclusive"} onChange={() => setForm({ ...form, bookingMode: "exclusive", maxQuantity: "" })} /><span>{text("独占预订", "Exclusive booking")}<small>{text("同一时段只允许一笔预订", "Allow only one booking in the same time slot")}</small></span></label><label><input type="radio" name="booking-mode" value="shared" checked={form.bookingMode === "shared"} onChange={() => setForm({ ...form, bookingMode: "shared" })} /><span>{text("共享数量", "Shared quantity")}<small>{text("同一时段按数量并行预订", "Allow concurrent bookings by quantity")}</small></span></label></div></fieldset>
          {form.bookingMode === "shared" && <div className="field span-2 conditional-field"><label htmlFor="resource-max">{text("最大可预订数量", "Maximum bookable quantity")} <b>*</b></label><input id="resource-max" type="number" min="1" step="1" required value={form.maxQuantity} onChange={(event) => setForm({ ...form, maxQuantity: event.target.value })} /><small>{text("所有重叠预订的数量之和不能超过此值。", "The total quantity of overlapping bookings cannot exceed this value.")}</small></div>}
        </div>
      </Drawer>
      <ConfirmDialog
        open={Boolean(archiving)}
        title={text(`归档“${archiving?.name ?? ""}”？`, `Archive “${archiving?.name ?? ""}”?`)}
        description={text("归档不会删除历史预订，但该资源将不再作为启用资源使用。", "Archiving keeps historical bookings, but this resource will no longer be available as active.")}
        busy={archive.isPending}
        error={archive.isError ? apiErrorMessage(archive.error) : null}
        onCancel={() => !archive.isPending && setArchiving(null)}
        onConfirm={() => archiving && archive.mutate(archiving.id)}
      />
    </div>
  );
}
