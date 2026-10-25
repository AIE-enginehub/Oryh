import { zhCN } from "../locales/zh-CN/console";
import { useRecordNotice } from "../components/master-data/RecordNotice";
import { useListFilters } from "../components/master-data/useListFilters";
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
  const { notice, notify } = useRecordNotice();
  const { keyword, status, page, setPage, applyFilters } = useListFilters<StatusFilter>(["active", "inactive", "archived"]);
  const [editing, setEditing] = useState<Resource | null | undefined>(undefined);
  const [archiving, setArchiving] = useState<Resource | null>(null);
  const [form, setForm] = useState<ResourceForm>(emptyForm);
  const [validationError, setValidationError] = useState<string | null>(null);

  const resources = useQuery({
    queryKey: ["master-data", "resources", { keyword, status, page }],
    queryFn: () => listResources({ page, size: PAGE_SIZE, keyword: keyword || undefined, status: status || "all" }),
    placeholderData: keepPreviousData,
  });
  const save = useMutation({
    mutationFn: ({ id, input }: { id?: string; input: CreateResourceInput }) =>
      id ? updateResource(id, input) : createResource(input),
    onSuccess: async (_resource, variables) => {
      setEditing(undefined);
      notify(variables.id ? "saved" : "created");
      if (!variables.id) setPage(1);
      await queryClient.invalidateQueries({ queryKey: ["master-data", "resources"] });
    },
  });
  const archive = useMutation({
    mutationFn: (id: string) => archiveResource(id),
    onSuccess: async () => {
      setArchiving(null);
      notify("archived");
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
      setValidationError(text(zhCN.pagesResourcesPage.resourceNameAndTypeAreRequired, "Resource name and type are required."));
      return;
    }
    const capacity = form.capacity ? Number(form.capacity) : null;
    const maxQuantity = form.maxQuantity ? Number(form.maxQuantity) : null;
    if (capacity !== null && (!Number.isInteger(capacity) || capacity < 1)) {
      setValidationError(text(zhCN.pagesResourcesPage.capacityMustBeAPositiveInteger, "Capacity must be a positive integer."));
      return;
    }
    if (form.bookingMode === "shared" && (maxQuantity === null || !Number.isInteger(maxQuantity) || maxQuantity < 1)) {
      setValidationError(text(zhCN.pagesResourcesPage.sharedResourcesRequireAPositiveMaximumBookableQuantity, "Shared resources require a positive maximum bookable quantity."));
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
        <div><span className="eyebrow">Resource registry</span><h2>{text(zhCN.pagesResourcesPage.resources, "Resources")}</h2><p>{text(zhCN.pagesResourcesPage.registerSpacesEquipmentAndSharedInventoryAndDefineThe, "Register spaces, equipment, and shared inventory, and define the capacity rules used for bookings.")}</p></div>
      </header>
      {notice}
      <section className="data-panel" aria-label={text(zhCN.pagesResourcesPage.resourceList, "Resource list")}>
        <ListToolbar
          keyword={keyword}
          status={status}
          placeholder={text(zhCN.pagesResourcesPage.searchResourceNames, "Search resource names")}
          createLabel={text(zhCN.pagesResourcesPage.newResource, "New resource")}
          statusOptions={[{ value: "active", label: text(zhCN.pagesResourcesPage.active, "Active") }, { value: "inactive", label: text(zhCN.pagesResourcesPage.inactive, "Inactive") }, { value: "archived", label: text(zhCN.pagesResourcesPage.archived, "Archived") }]}
          onCreate={openCreate}
          onApply={applyFilters}
        />
        <ListState
          loading={resources.isPending}
          error={resources.isError ? apiErrorMessage(resources.error) : null}
          empty={Boolean(result && result.data.length === 0)}
          emptyTitle={keyword || status ? text(zhCN.pagesResourcesPage.noMatchingResources, "No matching resources") : text(zhCN.pagesResourcesPage.noResourcesYet, "No resources yet")}
          emptyDescription={keyword || status ? text(zhCN.pagesResourcesPage.tryChangingYourSearchOrStatusFilter, "Try changing your search or status filter.") : text(zhCN.pagesResourcesPage.createAResourceSoEmployeesAndAgentsCanBook, "Create a resource so employees and agents can book it according to its rules.")}
          onRetry={() => void resources.refetch()}
        >
          {result && <>
            <div className="table-scroll"><table className="data-table">
              <thead><tr><th>{text(zhCN.pagesResourcesPage.resource, "Resource")}</th><th>{text(zhCN.pagesResourcesPage.typeLocation, "Type / Location")}</th><th>{text(zhCN.pagesResourcesPage.bookingRules, "Booking rules")}</th><th>{text(zhCN.pagesResourcesPage.status, "Status")}</th><th><span className="sr-only">{text(zhCN.pagesResourcesPage.actions, "Actions")}</span></th></tr></thead>
              <tbody>{result.data.map((resource) => (
                <tr key={resource.id}>
                  <td><button className="record-name" type="button" onClick={() => openEdit(resource)}>{resource.name}</button><small>{resource.code || text(zhCN.pagesResourcesPage.noCode, "No code")}</small></td>
                  <td><span>{resource.resource_type}</span><small>{resource.location || text(zhCN.pagesResourcesPage.noLocation, "No location")}{resource.capacity ? text(zhCN.pagesResourcesPage.capacity(`${resource.capacity}`), ` · Capacity ${resource.capacity}`) : ""}</small></td>
                  <td>{resource.booking_mode === "shared" ? <><span>{text(zhCN.pagesResourcesPage.sharedQuantity, "Shared quantity")}</span><small>{text(zhCN.pagesResourcesPage.upTo(`${resource.max_quantity ?? "—"}`), `Up to ${resource.max_quantity ?? "—"}`)}</small></> : <><span>{text(zhCN.pagesResourcesPage.exclusiveBooking, "Exclusive booking")}</span><small>{text(zhCN.pagesResourcesPage.oneBookingPerTimeSlot, "One booking per time slot")}</small></>}</td>
                  <td><StatusBadge status={resource.status} /></td>
                  <td className="row-actions"><button className="text-action" type="button" onClick={() => openEdit(resource)}>{text(zhCN.pagesResourcesPage.edit, "Edit")}</button>{resource.status !== "archived" && <button className="text-action danger-text" type="button" onClick={() => { archive.reset(); setArchiving(resource); }}>{text(zhCN.pagesResourcesPage.archive, "Archive")}</button>}</td>
                </tr>
              ))}</tbody>
            </table></div>
            <Pagination meta={result.meta} onPageChange={setPage} />
          </>}
        </ListState>
      </section>

      <Drawer
        open={editing !== undefined}
        title={editing ? text(zhCN.pagesResourcesPage.editResource, "Edit resource") : text(zhCN.pagesResourcesPage.newResource, "New resource")}
        description={editing ? text(zhCN.pagesResourcesPage.updateBookingMasterDataFor(`${editing.name}`), `Update booking master data for ${editing.name}.`) : text(zhCN.pagesResourcesPage.registerAResourceThatEmployeesOrAgentsCanBook, "Register a resource that employees or agents can book.")}
        submitLabel={editing ? text(zhCN.pagesResourcesPage.saveChanges, "Save changes") : text(zhCN.pagesResourcesPage.createResource, "Create resource")}
        busy={save.isPending}
        error={validationError || (save.isError ? apiErrorMessage(save.error) : null)}
        onClose={() => !save.isPending && setEditing(undefined)}
        onSubmit={submit}
      >
        <div className="field-grid">
          <div className="field span-2"><label htmlFor="resource-name">{text(zhCN.pagesResourcesPage.resourceName, "Resource name")} <b>*</b></label><input id="resource-name" required maxLength={200} value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} /></div>
          <div className="field"><label htmlFor="resource-type">{text(zhCN.pagesResourcesPage.resourceType, "Resource type")} <b>*</b></label><input id="resource-type" required maxLength={100} list="resource-types" value={form.type} onChange={(event) => setForm({ ...form, type: event.target.value })} /><datalist id="resource-types"><option value="meeting_room" /><option value="vehicle" /><option value="equipment" /><option value="inventory" /></datalist></div>
          <div className="field"><label htmlFor="resource-code">{text(zhCN.pagesResourcesPage.resourceCode, "Resource code")}</label><input id="resource-code" maxLength={64} value={form.code} onChange={(event) => setForm({ ...form, code: event.target.value })} /></div>
          <div className="field span-2"><label htmlFor="resource-location">{text(zhCN.pagesResourcesPage.location, "Location")}</label><input id="resource-location" maxLength={200} value={form.location} onChange={(event) => setForm({ ...form, location: event.target.value })} /></div>
          <div className="field"><label htmlFor="resource-capacity">{text(zhCN.pagesResourcesPage.occupancyCapacity, "Occupancy / Capacity")}</label><input id="resource-capacity" type="number" min="1" step="1" value={form.capacity} onChange={(event) => setForm({ ...form, capacity: event.target.value })} /></div>
          <div className="field"><label htmlFor="resource-status">{text(zhCN.pagesResourcesPage.status, "Status")}</label><select id="resource-status" value={form.status} onChange={(event) => setForm({ ...form, status: event.target.value as ResourceForm["status"] })}><option value="active">{text(zhCN.pagesResourcesPage.active, "Active")}</option><option value="inactive">{text(zhCN.pagesResourcesPage.inactive, "Inactive")}</option><option value="archived">{text(zhCN.pagesResourcesPage.archived, "Archived")}</option></select></div>
          <fieldset className="field span-2 booking-field"><legend>{text(zhCN.pagesResourcesPage.bookingMode, "Booking mode")}</legend><div className="segmented-control"><label><input type="radio" name="booking-mode" value="exclusive" checked={form.bookingMode === "exclusive"} onChange={() => setForm({ ...form, bookingMode: "exclusive", maxQuantity: "" })} /><span>{text(zhCN.pagesResourcesPage.exclusiveBooking, "Exclusive booking")}<small>{text(zhCN.pagesResourcesPage.allowOnlyOneBookingInTheSameTimeSlot, "Allow only one booking in the same time slot")}</small></span></label><label><input type="radio" name="booking-mode" value="shared" checked={form.bookingMode === "shared"} onChange={() => setForm({ ...form, bookingMode: "shared" })} /><span>{text(zhCN.pagesResourcesPage.sharedQuantity, "Shared quantity")}<small>{text(zhCN.pagesResourcesPage.allowConcurrentBookingsByQuantity, "Allow concurrent bookings by quantity")}</small></span></label></div></fieldset>
          {form.bookingMode === "shared" && <div className="field span-2 conditional-field"><label htmlFor="resource-max">{text(zhCN.pagesResourcesPage.maximumBookableQuantity, "Maximum bookable quantity")} <b>*</b></label><input id="resource-max" type="number" min="1" step="1" required value={form.maxQuantity} onChange={(event) => setForm({ ...form, maxQuantity: event.target.value })} /><small>{text(zhCN.pagesResourcesPage.theTotalQuantityOfOverlappingBookingsCannotExceedThis, "The total quantity of overlapping bookings cannot exceed this value.")}</small></div>}
        </div>
      </Drawer>
      <ConfirmDialog
        open={Boolean(archiving)}
        title={text(zhCN.pagesResourcesPage.archive2(`${archiving?.name ?? ""}`), `Archive “${archiving?.name ?? ""}”?`)}
        description={text(zhCN.pagesResourcesPage.archivingKeepsHistoricalBookingsButThisResourceWillNo, "Archiving keeps historical bookings, but this resource will no longer be available as active.")}
        busy={archive.isPending}
        error={archive.isError ? apiErrorMessage(archive.error) : null}
        onCancel={() => !archive.isPending && setArchiving(null)}
        onConfirm={() => archiving && archive.mutate(archiving.id)}
      />
    </div>
  );
}
