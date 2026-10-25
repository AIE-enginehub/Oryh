import { zhCN } from "../locales/zh-CN/console";
import { useRecordNotice } from "../components/master-data/RecordNotice";
import { useListFilters } from "../components/master-data/useListFilters";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import {
  archiveCustomer,
  createCustomer,
  listCustomers,
  updateCustomer,
  type CreateCustomerInput,
  type Customer,
} from "../api/client";
import { ConfirmDialog } from "../components/master-data/ConfirmDialog";
import { Drawer } from "../components/master-data/Drawer";
import { apiErrorMessage, ListState, StatusBadge } from "../components/master-data/ListState";
import { ListToolbar } from "../components/master-data/ListToolbar";
import { Pagination } from "../components/master-data/Pagination";
import { useI18n } from "../i18n";

const PAGE_SIZE = 20;
type StatusFilter = "" | "active" | "archived";
type CustomerForm = {
  name: string;
  code: string;
  taxId: string;
  contact: string;
  phone: string;
  email: string;
  address: string;
  status: Exclude<StatusFilter, "">;
};

const emptyForm: CustomerForm = { name: "", code: "", taxId: "", contact: "", phone: "", email: "", address: "", status: "active" };

function customerForm(customer?: Customer): CustomerForm {
  if (!customer) return emptyForm;
  return {
    name: customer.name,
    code: customer.customer_code ?? "",
    taxId: customer.tax_id ?? "",
    contact: customer.contact ?? "",
    phone: customer.phone ?? "",
    email: customer.email ?? "",
    address: customer.address ?? "",
    status: customer.status,
  };
}

export function CustomersPage() {
  const { text } = useI18n();
  const queryClient = useQueryClient();
  const { notice, notify } = useRecordNotice();
  const { keyword, status, page, setPage, applyFilters } = useListFilters<StatusFilter>(["active", "archived"]);
  const [editing, setEditing] = useState<Customer | null | undefined>(undefined);
  const [archiving, setArchiving] = useState<Customer | null>(null);
  const [form, setForm] = useState<CustomerForm>(emptyForm);
  const [validationError, setValidationError] = useState<string | null>(null);

  const customers = useQuery({
    queryKey: ["master-data", "customers", { keyword, status, page }],
    queryFn: () => listCustomers({ page, size: PAGE_SIZE, keyword: keyword || undefined, status: status || "all" }),
    placeholderData: keepPreviousData,
  });
  const save = useMutation({
    mutationFn: ({ id, input }: { id?: string; input: CreateCustomerInput }) =>
      id ? updateCustomer(id, input) : createCustomer(input),
    onSuccess: async (_customer, variables) => {
      setEditing(undefined);
      notify(variables.id ? "saved" : "created");
      if (!variables.id) setPage(1);
      await queryClient.invalidateQueries({ queryKey: ["master-data", "customers"] });
    },
  });
  const archive = useMutation({
    mutationFn: (id: string) => archiveCustomer(id),
    onSuccess: async () => {
      setArchiving(null);
      notify("archived");
      setPage(1);
      await queryClient.invalidateQueries({ queryKey: ["master-data", "customers"] });
    },
  });

  const openCreate = () => {
    setForm(emptyForm);
    setEditing(null);
    setValidationError(null);
    save.reset();
  };
  const openEdit = (customer: Customer) => {
    setForm(customerForm(customer));
    setEditing(customer);
    setValidationError(null);
    save.reset();
  };
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!form.name.trim()) {
      setValidationError(text(zhCN.pagesCustomersPage.customerNameIsRequired, "Customer name is required."));
      return;
    }
    if (form.email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email.trim())) {
      setValidationError(text(zhCN.pagesCustomersPage.enterAValidContactEmail, "Enter a valid contact email."));
      return;
    }
    setValidationError(null);
    save.mutate({
      id: editing?.id,
      input: {
        name: form.name.trim(),
        customer_code: form.code.trim() || null,
        tax_id: form.taxId.trim() || null,
        contact: form.contact.trim() || null,
        phone: form.phone.trim() || null,
        email: form.email.trim() || null,
        address: form.address.trim() || null,
        status: form.status,
      },
    });
  };

  const result = customers.data;
  return (
    <div className="master-data-page" data-testid="customers-page">
      <header className="page-intro">
        <div><span className="eyebrow">Customer registry</span><h2>{text(zhCN.pagesCustomersPage.customers, "Customers")}</h2><p>{text(zhCN.pagesCustomersPage.maintainCustomersTaxIDsAndContactsForAccurateSales, "Maintain customers, tax IDs, and contacts for accurate sales-quotation and invoicing workflows.")}</p></div>
      </header>
      {notice}
      <section className="data-panel" aria-label={text(zhCN.pagesCustomersPage.customerList, "Customer list")}>
        <ListToolbar
          keyword={keyword}
          status={status}
          placeholder={text(zhCN.pagesCustomersPage.searchCustomerNames, "Search customer names")}
          createLabel={text(zhCN.pagesCustomersPage.newCustomer, "New customer")}
          statusOptions={[{ value: "active", label: text(zhCN.pagesCustomersPage.active, "Active") }, { value: "archived", label: text(zhCN.pagesCustomersPage.archived, "Archived") }]}
          onCreate={openCreate}
          onApply={applyFilters}
        />
        <ListState
          loading={customers.isPending}
          error={customers.isError ? apiErrorMessage(customers.error) : null}
          empty={Boolean(result && result.data.length === 0)}
          emptyTitle={keyword || status ? text(zhCN.pagesCustomersPage.noMatchingCustomers, "No matching customers") : text(zhCN.pagesCustomersPage.noCustomersYet, "No customers yet")}
          emptyDescription={keyword || status ? text(zhCN.pagesCustomersPage.tryChangingYourSearchOrStatusFilter, "Try changing your search or status filter.") : text(zhCN.pagesCustomersPage.createACustomerSoAgentsCanMatchQuotationsAnd, "Create a customer so agents can match quotations and invoicing records.")}
          onRetry={() => void customers.refetch()}
        >
          {result && <>
            <div className="table-scroll"><table className="data-table">
              <thead><tr><th>{text(zhCN.pagesCustomersPage.customer, "Customer")}</th><th>{text(zhCN.pagesCustomersPage.taxID, "Tax ID")}</th><th>{text(zhCN.pagesCustomersPage.contact, "Contact")}</th><th>{text(zhCN.pagesCustomersPage.status, "Status")}</th><th><span className="sr-only">{text(zhCN.pagesCustomersPage.actions, "Actions")}</span></th></tr></thead>
              <tbody>{result.data.map((customer) => (
                <tr key={customer.id}>
                  <td><button className="record-name" type="button" onClick={() => openEdit(customer)}>{customer.name}</button><small>{customer.customer_code || text(zhCN.pagesCustomersPage.noCode, "No code")}</small></td>
                  <td className="mono-cell">{customer.tax_id || <span className="muted-value">—</span>}</td>
                  <td><span>{customer.contact || <span className="muted-value">—</span>}</span><small>{customer.email || customer.phone || text(zhCN.pagesCustomersPage.noContactDetails, "No contact details")}</small></td>
                  <td><StatusBadge status={customer.status} /></td>
                  <td className="row-actions"><button className="text-action" type="button" onClick={() => openEdit(customer)}>{text(zhCN.pagesCustomersPage.edit, "Edit")}</button>{customer.status !== "archived" && <button className="text-action danger-text" type="button" onClick={() => { archive.reset(); setArchiving(customer); }}>{text(zhCN.pagesCustomersPage.archive, "Archive")}</button>}</td>
                </tr>
              ))}</tbody>
            </table></div>
            <Pagination meta={result.meta} onPageChange={setPage} />
          </>}
        </ListState>
      </section>

      <Drawer
        open={editing !== undefined}
        title={editing ? text(zhCN.pagesCustomersPage.editCustomer, "Edit customer") : text(zhCN.pagesCustomersPage.newCustomer, "New customer")}
        description={editing ? text(zhCN.pagesCustomersPage.updateMasterDataFor(`${editing.name}`), `Update master data for ${editing.name}.`) : text(zhCN.pagesCustomersPage.registerACustomerForQuotationAndInvoicingWorkflows, "Register a customer for quotation and invoicing workflows.")}
        submitLabel={editing ? text(zhCN.pagesCustomersPage.saveChanges, "Save changes") : text(zhCN.pagesCustomersPage.createCustomer, "Create customer")}
        busy={save.isPending}
        error={validationError || (save.isError ? apiErrorMessage(save.error) : null)}
        onClose={() => !save.isPending && setEditing(undefined)}
        onSubmit={submit}
      >
        <div className="field-grid">
          <div className="field span-2"><label htmlFor="customer-name">{text(zhCN.pagesCustomersPage.customerName, "Customer name")} <b>*</b></label><input id="customer-name" required maxLength={200} value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} /></div>
          <div className="field"><label htmlFor="customer-code">{text(zhCN.pagesCustomersPage.customerCode, "Customer code")}</label><input id="customer-code" maxLength={64} value={form.code} onChange={(event) => setForm({ ...form, code: event.target.value })} /></div>
          <div className="field"><label htmlFor="customer-status">{text(zhCN.pagesCustomersPage.status, "Status")}</label><select id="customer-status" value={form.status} onChange={(event) => setForm({ ...form, status: event.target.value as CustomerForm["status"] })}><option value="active">{text(zhCN.pagesCustomersPage.active, "Active")}</option><option value="archived">{text(zhCN.pagesCustomersPage.archived, "Archived")}</option></select></div>
          <div className="field span-2"><label htmlFor="customer-tax">{text(zhCN.pagesCustomersPage.taxIDRegistrationNumber, "Tax ID / registration number")}</label><input id="customer-tax" maxLength={64} value={form.taxId} onChange={(event) => setForm({ ...form, taxId: event.target.value })} /></div>
          <div className="field span-2"><label htmlFor="customer-contact">{text(zhCN.pagesCustomersPage.contact, "Contact")}</label><input id="customer-contact" maxLength={200} value={form.contact} onChange={(event) => setForm({ ...form, contact: event.target.value })} /></div>
          <div className="field"><label htmlFor="customer-phone">{text(zhCN.pagesCustomersPage.phone, "Phone")}</label><input id="customer-phone" type="tel" maxLength={50} value={form.phone} onChange={(event) => setForm({ ...form, phone: event.target.value })} /></div>
          <div className="field"><label htmlFor="customer-email">{text(zhCN.pagesCustomersPage.email, "Email")}</label><input id="customer-email" type="email" maxLength={320} value={form.email} onChange={(event) => setForm({ ...form, email: event.target.value })} /></div>
          <div className="field span-2"><label htmlFor="customer-address">{text(zhCN.pagesCustomersPage.address, "Address")}</label><input id="customer-address" maxLength={500} value={form.address} onChange={(event) => setForm({ ...form, address: event.target.value })} /></div>
        </div>
      </Drawer>
      <ConfirmDialog
        open={Boolean(archiving)}
        title={text(zhCN.pagesCustomersPage.archive2(`${archiving?.name ?? ""}`), `Archive “${archiving?.name ?? ""}”?`)}
        description={text(zhCN.pagesCustomersPage.archivingPreservesHistoricalQuotationAndInvoicingReferencesButNew, "Archiving preserves historical quotation and invoicing references, but new workflows should not select this customer.")}
        busy={archive.isPending}
        error={archive.isError ? apiErrorMessage(archive.error) : null}
        onCancel={() => !archive.isPending && setArchiving(null)}
        onConfirm={() => archiving && archive.mutate(archiving.id)}
      />
    </div>
  );
}
