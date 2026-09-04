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
  const [keyword, setKeyword] = useState("");
  const [status, setStatus] = useState<StatusFilter>("");
  const [page, setPage] = useState(1);
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
      if (!variables.id) setPage(1);
      await queryClient.invalidateQueries({ queryKey: ["master-data", "customers"] });
    },
  });
  const archive = useMutation({
    mutationFn: (id: string) => archiveCustomer(id),
    onSuccess: async () => {
      setArchiving(null);
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
      setValidationError(text("客户名称不能为空。", "Customer name is required."));
      return;
    }
    if (form.email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email.trim())) {
      setValidationError(text("请输入有效的联系邮箱。", "Enter a valid contact email."));
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
        <div><span className="eyebrow">Customer registry</span><h2>{text("客户主数据", "Customer master data")}</h2><p>{text("集中维护客户、税号与联系人，支持销售报价与开票流程准确匹配。", "Maintain customers, tax IDs, and contacts for accurate sales-quotation and invoicing workflows.")}</p></div>
      </header>
      <section className="data-panel" aria-label={text("客户列表", "Customer list")}>
        <ListToolbar
          keyword={keyword}
          status={status}
          placeholder={text("按客户名称搜索", "Search customer names")}
          createLabel={text("新建客户", "New customer")}
          statusOptions={[{ value: "active", label: text("启用", "Active") }, { value: "archived", label: text("已归档", "Archived") }]}
          onCreate={openCreate}
          onApply={(filters) => { setKeyword(filters.keyword); setStatus(filters.status as StatusFilter); setPage(1); }}
        />
        <ListState
          loading={customers.isPending}
          error={customers.isError ? apiErrorMessage(customers.error) : null}
          empty={Boolean(result && result.data.length === 0)}
          emptyTitle={keyword || status ? text("没有匹配的客户", "No matching customers") : text("还没有客户", "No customers yet")}
          emptyDescription={keyword || status ? text("尝试调整搜索词或状态筛选。", "Try changing your search or status filter.") : text("新建客户后，代理可据此匹配报价和开票记录。", "Create a customer so agents can match quotations and invoicing records.")}
          onRetry={() => void customers.refetch()}
        >
          {result && <>
            <div className="table-scroll"><table className="data-table">
              <thead><tr><th>{text("客户", "Customer")}</th><th>{text("税号", "Tax ID")}</th><th>{text("联系人", "Contact")}</th><th>{text("状态", "Status")}</th><th><span className="sr-only">{text("操作", "Actions")}</span></th></tr></thead>
              <tbody>{result.data.map((customer) => (
                <tr key={customer.id}>
                  <td><strong>{customer.name}</strong><small>{customer.customer_code || text("未设置编号", "No code")}</small></td>
                  <td className="mono-cell">{customer.tax_id || <span className="muted-value">—</span>}</td>
                  <td><span>{customer.contact || <span className="muted-value">—</span>}</span><small>{customer.email || customer.phone || text("未设置联系方式", "No contact details")}</small></td>
                  <td><StatusBadge status={customer.status} /></td>
                  <td className="row-actions"><button className="text-action" type="button" onClick={() => openEdit(customer)}>{text("编辑", "Edit")}</button>{customer.status !== "archived" && <button className="text-action danger-text" type="button" onClick={() => { archive.reset(); setArchiving(customer); }}>{text("归档", "Archive")}</button>}</td>
                </tr>
              ))}</tbody>
            </table></div>
            <Pagination meta={result.meta} onPageChange={setPage} />
          </>}
        </ListState>
      </section>

      <Drawer
        open={editing !== undefined}
        title={editing ? text("编辑客户", "Edit customer") : text("新建客户", "New customer")}
        description={editing ? text(`更新 ${editing.name} 的主数据。`, `Update master data for ${editing.name}.`) : text("登记可供报价和开票流程引用的客户。", "Register a customer for quotation and invoicing workflows.")}
        submitLabel={editing ? text("保存更改", "Save changes") : text("创建客户", "Create customer")}
        busy={save.isPending}
        error={validationError || (save.isError ? apiErrorMessage(save.error) : null)}
        onClose={() => !save.isPending && setEditing(undefined)}
        onSubmit={submit}
      >
        <div className="field-grid">
          <div className="field span-2"><label htmlFor="customer-name">{text("客户名称", "Customer name")} <b>*</b></label><input id="customer-name" required maxLength={200} value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} /></div>
          <div className="field"><label htmlFor="customer-code">{text("客户编号", "Customer code")}</label><input id="customer-code" maxLength={64} value={form.code} onChange={(event) => setForm({ ...form, code: event.target.value })} /></div>
          <div className="field"><label htmlFor="customer-status">{text("状态", "Status")}</label><select id="customer-status" value={form.status} onChange={(event) => setForm({ ...form, status: event.target.value as CustomerForm["status"] })}><option value="active">{text("启用", "Active")}</option><option value="archived">{text("已归档", "Archived")}</option></select></div>
          <div className="field span-2"><label htmlFor="customer-tax">{text("税号 / 统一社会信用代码", "Tax ID / registration number")}</label><input id="customer-tax" maxLength={64} value={form.taxId} onChange={(event) => setForm({ ...form, taxId: event.target.value })} /></div>
          <div className="field span-2"><label htmlFor="customer-contact">{text("联系人", "Contact")}</label><input id="customer-contact" maxLength={200} value={form.contact} onChange={(event) => setForm({ ...form, contact: event.target.value })} /></div>
          <div className="field"><label htmlFor="customer-phone">{text("电话", "Phone")}</label><input id="customer-phone" type="tel" maxLength={50} value={form.phone} onChange={(event) => setForm({ ...form, phone: event.target.value })} /></div>
          <div className="field"><label htmlFor="customer-email">{text("邮箱", "Email")}</label><input id="customer-email" type="email" maxLength={320} value={form.email} onChange={(event) => setForm({ ...form, email: event.target.value })} /></div>
          <div className="field span-2"><label htmlFor="customer-address">{text("地址", "Address")}</label><input id="customer-address" maxLength={500} value={form.address} onChange={(event) => setForm({ ...form, address: event.target.value })} /></div>
        </div>
      </Drawer>
      <ConfirmDialog
        open={Boolean(archiving)}
        title={text(`归档“${archiving?.name ?? ""}”？`, `Archive “${archiving?.name ?? ""}”?`)}
        description={text("归档后不会删除历史报价或开票引用，但新流程不应再选择该客户。", "Archiving preserves historical quotation and invoicing references, but new workflows should not select this customer.")}
        busy={archive.isPending}
        error={archive.isError ? apiErrorMessage(archive.error) : null}
        onCancel={() => !archive.isPending && setArchiving(null)}
        onConfirm={() => archiving && archive.mutate(archiving.id)}
      />
    </div>
  );
}
