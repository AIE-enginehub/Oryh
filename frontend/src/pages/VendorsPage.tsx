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
  const [keyword, setKeyword] = useState("");
  const [status, setStatus] = useState<StatusFilter>("");
  const [page, setPage] = useState(1);
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
      if (!variables.id) setPage(1);
      await queryClient.invalidateQueries({ queryKey: ["master-data", "vendors"] });
    },
  });
  const archive = useMutation({
    mutationFn: (id: string) => archiveVendor(id),
    onSuccess: async () => {
      setArchiving(null);
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
      setValidationError(text("供应商名称不能为空。", "Vendor name is required."));
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
        <div><span className="eyebrow">Vendor registry</span><h2>{text("供应商主数据", "Vendor master data")}</h2><p>{text("集中维护供应商、税号与联系人，支持票据识别和采购流程准确匹配。", "Maintain vendors, tax IDs, and contacts for accurate receipt recognition and purchasing workflows.")}</p></div>
      </header>
      <section className="data-panel" aria-label={text("供应商列表", "Vendor list")}>
        <ListToolbar
          keyword={keyword}
          status={status}
          placeholder={text("按供应商名称搜索", "Search vendor names")}
          createLabel={text("新建供应商", "New vendor")}
          statusOptions={[{ value: "active", label: text("启用", "Active") }, { value: "archived", label: text("已归档", "Archived") }]}
          onCreate={openCreate}
          onApply={(filters) => { setKeyword(filters.keyword); setStatus(filters.status as StatusFilter); setPage(1); }}
        />
        <ListState
          loading={vendors.isPending}
          error={vendors.isError ? apiErrorMessage(vendors.error) : null}
          empty={Boolean(result && result.data.length === 0)}
          emptyTitle={keyword || status ? text("没有匹配的供应商", "No matching vendors") : text("还没有供应商", "No vendors yet")}
          emptyDescription={keyword || status ? text("尝试调整搜索词或状态筛选。", "Try changing your search or status filter.") : text("新建供应商后，代理可据此匹配票据和采购记录。", "Create a vendor so agents can match receipts and purchase records.")}
          onRetry={() => void vendors.refetch()}
        >
          {result && <>
            <div className="table-scroll"><table className="data-table">
              <thead><tr><th>{text("供应商", "Vendor")}</th><th>{text("税号", "Tax ID")}</th><th>{text("联系人", "Contact")}</th><th>{text("状态", "Status")}</th><th><span className="sr-only">{text("操作", "Actions")}</span></th></tr></thead>
              <tbody>{result.data.map((vendor) => (
                <tr key={vendor.id}>
                  <td><strong>{vendor.name}</strong><small>{vendor.vendor_code || text("未设置编号", "No code")}</small></td>
                  <td className="mono-cell">{vendor.tax_id || <span className="muted-value">—</span>}</td>
                  <td><span>{vendor.contact || <span className="muted-value">—</span>}</span><small>{vendor.email || vendor.phone || text("未设置联系方式", "No contact details")}</small></td>
                  <td><StatusBadge status={vendor.status} /></td>
                  <td className="row-actions"><button className="text-action" type="button" onClick={() => openEdit(vendor)}>{text("编辑", "Edit")}</button>{vendor.status !== "archived" && <button className="text-action danger-text" type="button" onClick={() => { archive.reset(); setArchiving(vendor); }}>{text("归档", "Archive")}</button>}</td>
                </tr>
              ))}</tbody>
            </table></div>
            <Pagination meta={result.meta} onPageChange={setPage} />
          </>}
        </ListState>
      </section>

      <Drawer
        open={editing !== undefined}
        title={editing ? text("编辑供应商", "Edit vendor") : text("新建供应商", "New vendor")}
        description={editing ? text(`更新 ${editing.name} 的主数据。`, `Update master data for ${editing.name}.`) : text("登记可供采购和票据流程引用的供应商。", "Register a vendor for purchasing and receipt workflows.")}
        submitLabel={editing ? text("保存更改", "Save changes") : text("创建供应商", "Create vendor")}
        busy={save.isPending}
        error={validationError || (save.isError ? apiErrorMessage(save.error) : null)}
        onClose={() => !save.isPending && setEditing(undefined)}
        onSubmit={submit}
      >
        <div className="field-grid">
          <div className="field span-2"><label htmlFor="vendor-name">{text("供应商名称", "Vendor name")} <b>*</b></label><input id="vendor-name" required maxLength={200} value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} /></div>
          <div className="field"><label htmlFor="vendor-code">{text("供应商编号", "Vendor code")}</label><input id="vendor-code" maxLength={64} value={form.code} onChange={(event) => setForm({ ...form, code: event.target.value })} /></div>
          <div className="field"><label htmlFor="vendor-status">{text("状态", "Status")}</label><select id="vendor-status" value={form.status} onChange={(event) => setForm({ ...form, status: event.target.value as VendorForm["status"] })}><option value="active">{text("启用", "Active")}</option><option value="archived">{text("已归档", "Archived")}</option></select></div>
          <div className="field span-2"><label htmlFor="vendor-tax">{text("税号 / 统一社会信用代码", "Tax ID / registration number")}</label><input id="vendor-tax" maxLength={64} value={form.taxId} onChange={(event) => setForm({ ...form, taxId: event.target.value })} /></div>
          <div className="field span-2"><label htmlFor="vendor-contact">{text("联系人", "Contact")}</label><input id="vendor-contact" maxLength={200} value={form.contact} onChange={(event) => setForm({ ...form, contact: event.target.value })} /></div>
          <div className="field"><label htmlFor="vendor-phone">{text("电话", "Phone")}</label><input id="vendor-phone" type="tel" maxLength={50} value={form.phone} onChange={(event) => setForm({ ...form, phone: event.target.value })} /></div>
          <div className="field"><label htmlFor="vendor-email">{text("邮箱", "Email")}</label><input id="vendor-email" type="email" maxLength={320} value={form.email} onChange={(event) => setForm({ ...form, email: event.target.value })} /></div>
        </div>
      </Drawer>
      <ConfirmDialog
        open={Boolean(archiving)}
        title={text(`归档“${archiving?.name ?? ""}”？`, `Archive “${archiving?.name ?? ""}”?`)}
        description={text("归档后不会删除历史采购或票据引用，但新流程不应再选择该供应商。", "Archiving preserves historical purchase and receipt references, but new workflows should not select this vendor.")}
        busy={archive.isPending}
        error={archive.isError ? apiErrorMessage(archive.error) : null}
        onCancel={() => !archive.isPending && setArchiving(null)}
        onConfirm={() => archiving && archive.mutate(archiving.id)}
      />
    </div>
  );
}
