import { zhCN } from "../locales/zh-CN/console";
import { useRecordNotice } from "../components/master-data/RecordNotice";
import { useListFilters } from "../components/master-data/useListFilters";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import {
  archiveVendor,
  createVendor,
  listVendors,
  updateVendor,
  type CreateVendorInput,
  type Vendor,
} from "../api/client";
import { ConfirmDialog } from "../components/master-data/ConfirmDialog";
import { Drawer } from "../components/master-data/Drawer";
import { apiErrorMessage, ListState, StatusBadge } from "../components/master-data/ListState";
import { ListToolbar } from "../components/master-data/ListToolbar";
import { Pagination } from "../components/master-data/Pagination";
import { useI18n } from "../i18n";

const PAGE_SIZE = 20;
type StatusFilter = "" | "active" | "archived";
type VendorForm = {
  name: string;
  code: string;
  taxId: string;
  contact: string;
  phone: string;
  email: string;
  status: Exclude<StatusFilter, "">;
};

const emptyForm: VendorForm = { name: "", code: "", taxId: "", contact: "", phone: "", email: "", status: "active" };

function vendorForm(vendor?: Vendor): VendorForm {
  if (!vendor) return emptyForm;
  return {
    name: vendor.name,
    code: vendor.vendor_code ?? "",
    taxId: vendor.tax_id ?? "",
    contact: vendor.contact ?? "",
    phone: vendor.phone ?? "",
    email: vendor.email ?? "",
    status: vendor.status,
  };
}

export function VendorsPage() {
  const { text } = useI18n();
  const queryClient = useQueryClient();
  const { notice, notify } = useRecordNotice();
  const { keyword, status, page, setPage, applyFilters } = useListFilters<StatusFilter>(["active", "archived"]);
  const [editing, setEditing] = useState<Vendor | null | undefined>(undefined);
  const [archiving, setArchiving] = useState<Vendor | null>(null);
  const [form, setForm] = useState<VendorForm>(emptyForm);
  const [validationError, setValidationError] = useState<string | null>(null);

  const vendors = useQuery({
    queryKey: ["master-data", "vendors", { keyword, status, page }],
    queryFn: () => listVendors({ page, size: PAGE_SIZE, keyword: keyword || undefined, status: status || "all" }),
    placeholderData: keepPreviousData,
  });
  const save = useMutation({
    mutationFn: ({ id, input }: { id?: string; input: CreateVendorInput }) =>
      id ? updateVendor(id, input) : createVendor(input),
    onSuccess: async (_vendor, variables) => {
      setEditing(undefined);
      notify(variables.id ? "saved" : "created");
      if (!variables.id) setPage(1);
      await queryClient.invalidateQueries({ queryKey: ["master-data", "vendors"] });
    },
  });
  const archive = useMutation({
    mutationFn: (id: string) => archiveVendor(id),
    onSuccess: async () => {
      setArchiving(null);
      notify("archived");
      setPage(1);
      await queryClient.invalidateQueries({ queryKey: ["master-data", "vendors"] });
    },
  });

  const openCreate = () => {
    setForm(emptyForm);
    setEditing(null);
    setValidationError(null);
    save.reset();
  };
  const openEdit = (vendor: Vendor) => {
    setForm(vendorForm(vendor));
    setEditing(vendor);
    setValidationError(null);
    save.reset();
  };
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!form.name.trim()) {
      setValidationError(text(zhCN.pagesVendorsPage.vendorNameIsRequired, "Vendor name is required."));
      return;
    }
    if (form.email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email.trim())) {
      setValidationError(text(zhCN.pagesVendorsPage.enterAValidContactEmail, "Enter a valid contact email."));
      return;
    }
    setValidationError(null);
    save.mutate({
      id: editing?.id,
      input: {
        name: form.name.trim(),
        vendor_code: form.code.trim() || null,
        tax_id: form.taxId.trim() || null,
        contact: form.contact.trim() || null,
        phone: form.phone.trim() || null,
        email: form.email.trim() || null,
        status: form.status,
      },
    });
  };

  const result = vendors.data;
  return (
    <div className="master-data-page" data-testid="vendors-page">
      <header className="page-intro">
        <div><span className="eyebrow">Vendor registry</span><h2>{text(zhCN.pagesVendorsPage.vendors, "Vendors")}</h2><p>{text(zhCN.pagesVendorsPage.maintainVendorsTaxIDsAndContactsForAccurateReceipt, "Maintain vendors, tax IDs, and contacts for accurate receipt recognition and purchasing workflows.")}</p></div>
      </header>
      {notice}
      <section className="data-panel" aria-label={text(zhCN.pagesVendorsPage.vendorList, "Vendor list")}>
        <ListToolbar
          keyword={keyword}
          status={status}
          placeholder={text(zhCN.pagesVendorsPage.searchVendorNames, "Search vendor names")}
          createLabel={text(zhCN.pagesVendorsPage.newVendor, "New vendor")}
          statusOptions={[{ value: "active", label: text(zhCN.pagesVendorsPage.active, "Active") }, { value: "archived", label: text(zhCN.pagesVendorsPage.archived, "Archived") }]}
          onCreate={openCreate}
          onApply={applyFilters}
        />
        <ListState
          loading={vendors.isPending}
          error={vendors.isError ? apiErrorMessage(vendors.error) : null}
          empty={Boolean(result && result.data.length === 0)}
          emptyTitle={keyword || status ? text(zhCN.pagesVendorsPage.noMatchingVendors, "No matching vendors") : text(zhCN.pagesVendorsPage.noVendorsYet, "No vendors yet")}
          emptyDescription={keyword || status ? text(zhCN.pagesVendorsPage.tryChangingYourSearchOrStatusFilter, "Try changing your search or status filter.") : text(zhCN.pagesVendorsPage.createAVendorSoAgentsCanMatchReceiptsAnd, "Create a vendor so agents can match receipts and purchase records.")}
          onRetry={() => void vendors.refetch()}
        >
          {result && <>
            <div className="table-scroll"><table className="data-table">
              <thead><tr><th>{text(zhCN.pagesVendorsPage.vendor, "Vendor")}</th><th>{text(zhCN.pagesVendorsPage.taxID, "Tax ID")}</th><th>{text(zhCN.pagesVendorsPage.contact, "Contact")}</th><th>{text(zhCN.pagesVendorsPage.status, "Status")}</th><th><span className="sr-only">{text(zhCN.pagesVendorsPage.actions, "Actions")}</span></th></tr></thead>
              <tbody>{result.data.map((vendor) => (
                <tr key={vendor.id}>
                  <td><button className="record-name" type="button" onClick={() => openEdit(vendor)}>{vendor.name}</button><small>{vendor.vendor_code || text(zhCN.pagesVendorsPage.noCode, "No code")}</small></td>
                  <td className="mono-cell">{vendor.tax_id || <span className="muted-value">—</span>}</td>
                  <td><span>{vendor.contact || <span className="muted-value">—</span>}</span><small>{vendor.email || vendor.phone || text(zhCN.pagesVendorsPage.noContactDetails, "No contact details")}</small></td>
                  <td><StatusBadge status={vendor.status} /></td>
                  <td className="row-actions"><button className="text-action" type="button" onClick={() => openEdit(vendor)}>{text(zhCN.pagesVendorsPage.edit, "Edit")}</button>{vendor.status !== "archived" && <button className="text-action danger-text" type="button" onClick={() => { archive.reset(); setArchiving(vendor); }}>{text(zhCN.pagesVendorsPage.archive, "Archive")}</button>}</td>
                </tr>
              ))}</tbody>
            </table></div>
            <Pagination meta={result.meta} onPageChange={setPage} />
          </>}
        </ListState>
      </section>

      <Drawer
        open={editing !== undefined}
        title={editing ? text(zhCN.pagesVendorsPage.editVendor, "Edit vendor") : text(zhCN.pagesVendorsPage.newVendor, "New vendor")}
        description={editing ? text(zhCN.pagesVendorsPage.updateMasterDataFor(`${editing.name}`), `Update master data for ${editing.name}.`) : text(zhCN.pagesVendorsPage.registerAVendorForPurchasingAndReceiptWorkflows, "Register a vendor for purchasing and receipt workflows.")}
        submitLabel={editing ? text(zhCN.pagesVendorsPage.saveChanges, "Save changes") : text(zhCN.pagesVendorsPage.createVendor, "Create vendor")}
        busy={save.isPending}
        error={validationError || (save.isError ? apiErrorMessage(save.error) : null)}
        onClose={() => !save.isPending && setEditing(undefined)}
        onSubmit={submit}
      >
        <div className="field-grid">
          <div className="field span-2"><label htmlFor="vendor-name">{text(zhCN.pagesVendorsPage.vendorName, "Vendor name")} <b>*</b></label><input id="vendor-name" required maxLength={200} value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} /></div>
          <div className="field"><label htmlFor="vendor-code">{text(zhCN.pagesVendorsPage.vendorCode, "Vendor code")}</label><input id="vendor-code" maxLength={64} value={form.code} onChange={(event) => setForm({ ...form, code: event.target.value })} /></div>
          <div className="field"><label htmlFor="vendor-status">{text(zhCN.pagesVendorsPage.status, "Status")}</label><select id="vendor-status" value={form.status} onChange={(event) => setForm({ ...form, status: event.target.value as VendorForm["status"] })}><option value="active">{text(zhCN.pagesVendorsPage.active, "Active")}</option><option value="archived">{text(zhCN.pagesVendorsPage.archived, "Archived")}</option></select></div>
          <div className="field span-2"><label htmlFor="vendor-tax">{text(zhCN.pagesVendorsPage.taxIDRegistrationNumber, "Tax ID / registration number")}</label><input id="vendor-tax" maxLength={64} value={form.taxId} onChange={(event) => setForm({ ...form, taxId: event.target.value })} /></div>
          <div className="field span-2"><label htmlFor="vendor-contact">{text(zhCN.pagesVendorsPage.contact, "Contact")}</label><input id="vendor-contact" maxLength={200} value={form.contact} onChange={(event) => setForm({ ...form, contact: event.target.value })} /></div>
          <div className="field"><label htmlFor="vendor-phone">{text(zhCN.pagesVendorsPage.phone, "Phone")}</label><input id="vendor-phone" type="tel" maxLength={50} value={form.phone} onChange={(event) => setForm({ ...form, phone: event.target.value })} /></div>
          <div className="field"><label htmlFor="vendor-email">{text(zhCN.pagesVendorsPage.email, "Email")}</label><input id="vendor-email" type="email" maxLength={320} value={form.email} onChange={(event) => setForm({ ...form, email: event.target.value })} /></div>
        </div>
      </Drawer>
      <ConfirmDialog
        open={Boolean(archiving)}
        title={text(zhCN.pagesVendorsPage.archive2(`${archiving?.name ?? ""}`), `Archive “${archiving?.name ?? ""}”?`)}
        description={text(zhCN.pagesVendorsPage.archivingPreservesHistoricalPurchaseAndReceiptReferencesButNew, "Archiving preserves historical purchase and receipt references, but new workflows should not select this vendor.")}
        busy={archive.isPending}
        error={archive.isError ? apiErrorMessage(archive.error) : null}
        onCancel={() => !archive.isPending && setArchiving(null)}
        onConfirm={() => archiving && archive.mutate(archiving.id)}
      />
    </div>
  );
}
