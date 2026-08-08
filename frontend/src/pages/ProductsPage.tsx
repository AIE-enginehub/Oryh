import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, type FormEvent } from "react";

import {
  archiveProduct,
  archiveProductSku,
  batchCreateProductSkus,
  createProduct,
  createProductSku,
  listProducts,
  listProductSkus,
  updateProduct,
  updateProductSku,
  type BatchCreateProductSkusInput,
  type BatchCreateProductSkusResult,
  type CreateProductInput,
  type CreateProductSkuInput,
  type Product,
  type ProductSku,
  type UpdateProductSkuInput,
} from "../api/client";
import {
  attributesToRows,
  emptyAttributeRow,
  VariantAttributesEditor,
  type AttributeRow,
} from "../components/products/VariantAttributesEditor";
import { ProductDetailPanel } from "../components/products/ProductDetailPanel";
import { ConfirmDialog } from "../components/master-data/ConfirmDialog";
import { Drawer } from "../components/master-data/Drawer";
import { apiErrorMessage, ListState, StatusBadge } from "../components/master-data/ListState";
import { ListToolbar } from "../components/master-data/ListToolbar";
import { Pagination } from "../components/master-data/Pagination";
import { useI18n } from "../i18n";
import "./products.css";

const PAGE_SIZE = 20;
const MAX_PRICE = 9_999_999.99;
type StatusFilter = "" | "active" | "archived";
type ActiveStatus = Exclude<StatusFilter, "">;

type ProductForm = {
  name: string;
  code: string;
  spec: string;
  unit: string;
  price: string;
  currency: string;
  status: ActiveStatus;
};

type SkuForm = {
  code: string;
  price: string;
  status: ActiveStatus;
  attributes: AttributeRow[];
};

type BatchSkuForm = {
  dimension: string;
  values: string;
  price: string;
};

type BatchSkuNotice = BatchCreateProductSkusResult & {
  productId: string;
  dimension: string;
};

const emptyProductForm: ProductForm = {
  name: "",
  code: "",
  spec: "",
  unit: "",
  price: "",
  currency: "CNY",
  status: "active",
};

const emptySkuForm = (): SkuForm => ({
  code: "",
  price: "",
  status: "active",
  attributes: [emptyAttributeRow()],
});

const emptyBatchSkuForm = (dimension: string): BatchSkuForm => ({
  dimension,
  values: "",
  price: "",
});

function toProductForm(product?: Product): ProductForm {
  if (!product) return emptyProductForm;
  return {
    name: product.name,
    code: product.product_code ?? "",
    spec: product.spec ?? "",
    unit: product.unit ?? "",
    price: product.list_price?.toString() ?? "",
    currency: product.currency,
    status: product.status,
  };
}

function toSkuForm(sku?: ProductSku): SkuForm {
  if (!sku) return emptySkuForm();
  return {
    code: sku.sku_code ?? "",
    price: sku.list_price?.toString() ?? "",
    status: sku.status,
    attributes: attributesToRows(sku.variant_attrs),
  };
}

type LocalText = (chinese: string, english: string) => string;

function parsePrice(raw: string, text: LocalText): { value: number | null; error: string | null } {
  const normalized = raw.trim();
  if (!normalized) return { value: null, error: null };
  if (!/^\d+(\.\d{1,2})?$/.test(normalized)) {
    return { value: null, error: text("价格最多保留两位小数。", "Prices can have at most two decimal places.") };
  }
  const value = Number(normalized);
  if (!Number.isFinite(value) || value < 0 || value > MAX_PRICE) {
    return { value: null, error: text(`价格必须在 0 到 ${MAX_PRICE.toLocaleString()} 之间。`, `Price must be between 0 and ${MAX_PRICE.toLocaleString()}.`) };
  }
  return { value, error: null };
}

function buildAttributes(rows: AttributeRow[], text: LocalText): { value: Record<string, unknown>; error: string | null } {
  const value: Record<string, unknown> = {};
  for (const row of rows) {
    const key = row.key.trim();
    const attributeValue = row.value.trim();
    if (!key && !attributeValue) continue;
    if (!key || !attributeValue) {
      return { value: {}, error: text("每一行规格属性都需要同时填写名称和值。", "Every variant attribute row requires both a name and a value.") };
    }
    if (Object.prototype.hasOwnProperty.call(value, key)) {
      return { value: {}, error: text(`规格属性“${key}”重复，请合并后再保存。`, `Variant attribute “${key}” is duplicated. Merge it before saving.`) };
    }
    if (row.valueType === "json") {
      try {
        value[key] = JSON.parse(attributeValue) as unknown;
      } catch {
        return { value: {}, error: text(`规格属性“${key}”包含结构化内容，请按原有格式填写。`, `Variant attribute “${key}” contains structured content. Keep the original format.`) };
      }
    } else {
      value[key] = attributeValue;
    }
  }
  return { value, error: null };
}

function splitBatchValues(raw: string): string[] {
  return raw.split(/[,，、;；\/\s]+/).map((value) => value.trim()).filter(Boolean);
}

function batchSkuLabel(sku: ProductSku, dimension: string): string {
  if (sku.sku_code) return sku.sku_code;
  const value = sku.variant_attrs[dimension];
  if (typeof value === "string" || typeof value === "number") return String(value);
  if (value != null) return JSON.stringify(value) ?? sku.id;
  return sku.id;
}

function formatMoney(value: number | null | undefined, currency: string, locale = "zh-CN"): string {
  if (value == null) return "—";
  try {
    return new Intl.NumberFormat(locale, { style: "currency", currency }).format(value);
  } catch {
    return `${currency} ${value.toFixed(2)}`;
  }
}

function AttributeSummary({ attributes }: { attributes: Record<string, unknown> }) {
  const { text } = useI18n();
  const entries = Object.entries(attributes);
  if (entries.length === 0) return <span className="muted-value">{text("未设置规格", "No variants")}</span>;
  return (
    <div className="variant-summary">
      {entries.map(([key, value]) => (
        <span className="variant-chip" key={key}>
          {key}{text("：", ": ")}{typeof value === "string" ? value : (JSON.stringify(value) ?? String(value))}
        </span>
      ))}
    </div>
  );
}

export function ProductsPage() {
  const { language, text } = useI18n();
  const queryClient = useQueryClient();
  const [keyword, setKeyword] = useState("");
  const [status, setStatus] = useState<StatusFilter>("");
  const [page, setPage] = useState(1);
  const [selectedProduct, setSelectedProduct] = useState<Product | null>(null);
  const [viewingProduct, setViewingProduct] = useState<Product | null>(null);
  const [editingProduct, setEditingProduct] = useState<Product | null | undefined>(undefined);
  const [archivingProduct, setArchivingProduct] = useState<Product | null>(null);
  const [productForm, setProductForm] = useState<ProductForm>(emptyProductForm);
  const [productValidation, setProductValidation] = useState<string | null>(null);

  const [skuStatus, setSkuStatus] = useState<StatusFilter>("");
  const [skuCode, setSkuCode] = useState("");
  const [skuCodeDraft, setSkuCodeDraft] = useState("");
  const [skuPage, setSkuPage] = useState(1);
  const [editingSku, setEditingSku] = useState<ProductSku | null | undefined>(undefined);
  const [archivingSku, setArchivingSku] = useState<ProductSku | null>(null);
  const [skuForm, setSkuForm] = useState<SkuForm>(emptySkuForm);
  const [skuValidation, setSkuValidation] = useState<string | null>(null);
  const [batchOpen, setBatchOpen] = useState(false);
  const [batchForm, setBatchForm] = useState<BatchSkuForm>(() => emptyBatchSkuForm(text("尺码", "Size")));
  const [batchValidation, setBatchValidation] = useState<string | null>(null);
  const [batchNotice, setBatchNotice] = useState<BatchSkuNotice | null>(null);

  const products = useQuery({
    queryKey: ["master-data", "products", { keyword, status, page }],
    queryFn: () => listProducts({ page, size: PAGE_SIZE, keyword: keyword || undefined, status: status || undefined }),
    placeholderData: keepPreviousData,
  });

  const skus = useQuery({
    queryKey: ["master-data", "product-skus", selectedProduct?.id, { skuCode, skuStatus, skuPage }],
    queryFn: () => listProductSkus({
      product_id: selectedProduct!.id,
      page: skuPage,
      size: PAGE_SIZE,
      sku_code: skuCode || undefined,
      status: skuStatus || undefined,
    }),
    enabled: selectedProduct !== null,
  });

  const productPages = products.data?.meta.pages;
  useEffect(() => {
    if (productPages !== undefined && page > productPages) {
      setPage(Math.max(productPages, 1));
    }
  }, [page, productPages]);

  const skuPages = skus.data?.meta.pages;
  useEffect(() => {
    if (selectedProduct && skuPages !== undefined && skuPage > skuPages) {
      setSkuPage(Math.max(skuPages, 1));
    }
  }, [selectedProduct, skuPage, skuPages]);

  const saveProduct = useMutation({
    mutationFn: ({ id, input }: { id?: string; input: CreateProductInput }) =>
      id ? updateProduct(id, input) : createProduct(input),
    onSuccess: async (saved, variables) => {
      setEditingProduct(undefined);
      if (!variables.id) setPage(1);
      setSelectedProduct((current: Product | null) => current?.id === saved.id ? saved : current);
      await queryClient.invalidateQueries({ queryKey: ["master-data", "products"] });
    },
  });

  const archiveProductMutation = useMutation({
    mutationFn: (id: string) => archiveProduct(id),
    onSuccess: async (_, id) => {
      setArchivingProduct(null);
      setPage(1);
      if (selectedProduct?.id === id) setSelectedProduct(null);
      await queryClient.invalidateQueries({ queryKey: ["master-data", "products"] });
    },
  });

  type SkuSaveVariables =
    | { mode: "create"; input: CreateProductSkuInput }
    | { mode: "update"; id: string; input: UpdateProductSkuInput };

  const saveSku = useMutation({
    mutationFn: (variables: SkuSaveVariables) => variables.mode === "update"
      ? updateProductSku(variables.id, variables.input)
      : createProductSku(variables.input),
    onSuccess: async (_, variables) => {
      setEditingSku(undefined);
      if (variables.mode === "create") {
        setSkuPage(1);
        setSelectedProduct((current: Product | null) => current ? { ...current, has_skus: true, sku_count: current.sku_count + 1 } : current);
      }
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["master-data", "product-skus", selectedProduct?.id] }),
        queryClient.invalidateQueries({ queryKey: ["master-data", "products"] }),
      ]);
    },
  });

  const batchCreateSku = useMutation({
    mutationFn: ({ productId, input }: { productId: string; input: BatchCreateProductSkusInput }) =>
      batchCreateProductSkus(productId, input),
    onSuccess: async (result, variables) => {
      setBatchOpen(false);
      setBatchNotice({
        productId: variables.productId,
        dimension: variables.input.dimension,
        ...result,
      });
      setSkuPage(1);
      setSelectedProduct((current: Product | null) => current?.id === variables.productId
        ? { ...current, has_skus: true, sku_count: current.sku_count + result.created.length }
        : current);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["master-data", "product-skus", variables.productId] }),
        queryClient.invalidateQueries({ queryKey: ["master-data", "products"] }),
      ]);
    },
  });

  const archiveSkuMutation = useMutation({
    mutationFn: (id: string) => archiveProductSku(id),
    onSuccess: async () => {
      setArchivingSku(null);
      setSkuPage(1);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["master-data", "product-skus", selectedProduct?.id] }),
        queryClient.invalidateQueries({ queryKey: ["master-data", "products"] }),
      ]);
    },
  });

  const selectProduct = (product: Product) => {
    setSelectedProduct(product);
    setSkuStatus("");
    setSkuCode("");
    setSkuCodeDraft("");
    setSkuPage(1);
    setBatchNotice(null);
  };

  const openCreateProduct = () => {
    setProductForm(emptyProductForm);
    setProductValidation(null);
    setEditingProduct(null);
    saveProduct.reset();
  };
  const openEditProduct = (product: Product) => {
    setProductForm(toProductForm(product));
    setProductValidation(null);
    setEditingProduct(product);
    saveProduct.reset();
  };
  const submitProduct = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const name = productForm.name.trim();
    const currency = productForm.currency.trim().toUpperCase();
    if (!name) {
      setProductValidation(text("产品名称不能为空。", "Product name is required."));
      return;
    }
    if (!/^[A-Z]{3}$/.test(currency)) {
      setProductValidation(text("币种必须是三位 ISO 代码，例如 CNY、USD。", "Currency must be a three-letter ISO code, such as CNY or USD."));
      return;
    }
    const price = parsePrice(productForm.price, text);
    if (price.error) {
      setProductValidation(price.error);
      return;
    }
    setProductValidation(null);
    saveProduct.mutate({
      id: editingProduct?.id,
      input: {
        name,
        product_code: productForm.code.trim() || null,
        spec: productForm.spec.trim() || null,
        unit: productForm.unit.trim() || null,
        list_price: price.value,
        currency,
        status: productForm.status,
      },
    });
  };

  const openCreateSku = () => {
    setSkuForm(emptySkuForm());
    setSkuValidation(null);
    setEditingSku(null);
    saveSku.reset();
  };

  const openBatchCreateSku = () => {
    if (!selectedProduct) return;
    setBatchForm(emptyBatchSkuForm(text("尺码", "Size")));
    setBatchValidation(null);
    setBatchNotice(null);
    batchCreateSku.reset();
    setBatchOpen(true);
  };
  const openEditSku = (sku: ProductSku) => {
    setSkuForm(toSkuForm(sku));
    setSkuValidation(null);
    setEditingSku(sku);
    saveSku.reset();
  };
  const submitSku = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!selectedProduct) return;
    const attributes = buildAttributes(skuForm.attributes, text);
    if (attributes.error) {
      setSkuValidation(attributes.error);
      return;
    }
    const code = skuForm.code.trim();
    if (!code && Object.keys(attributes.value).length === 0) {
      setSkuValidation(text("请填写 SKU 编码，或至少添加一项规格属性。", "Enter a SKU code or add at least one variant attribute."));
      return;
    }
    const price = parsePrice(skuForm.price, text);
    if (price.error) {
      setSkuValidation(price.error);
      return;
    }
    setSkuValidation(null);
    const input = {
      sku_code: code || null,
      variant_attrs: attributes.value,
      list_price: price.value,
      status: skuForm.status,
    };
    if (editingSku) {
      const updateInput: UpdateProductSkuInput = input;
      saveSku.mutate({ mode: "update", id: editingSku.id, input: updateInput });
    } else {
      const createInput: CreateProductSkuInput = { ...input, product_id: selectedProduct.id };
      saveSku.mutate({ mode: "create", input: createInput });
    }
  };

  const submitBatchSku = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!selectedProduct) return;
    const dimension = batchForm.dimension.trim();
    const values = splitBatchValues(batchForm.values);
    if (!dimension) {
      setBatchValidation(text("请填写配码维度，例如尺码或颜色。", "Enter a variant dimension, such as size or color."));
      return;
    }
    if (values.length === 0) {
      setBatchValidation(text("请至少填写一个规格值。", "Enter at least one variant value."));
      return;
    }
    const price = parsePrice(batchForm.price, text);
    if (price.error) {
      setBatchValidation(price.error);
      return;
    }
    setBatchValidation(null);
    batchCreateSku.mutate({
      productId: selectedProduct.id,
      input: { dimension, values, list_price: price.value },
    });
  };

  const productResult = products.data;
  const skuResult = skus.data;
  return (
    <div className="product-workspace" data-testid="products-page">
      <header className="page-intro">
        <div><span className="eyebrow">Product catalog</span><h2>{text("产品与 SKU", "Products and SKUs")}</h2><p>{text("先维护产品级信息，再为颜色、尺码或其他可交易变体建立 SKU。", "Maintain product-level information, then create SKUs for colors, sizes, or other sellable variants.")}</p></div>
      </header>

      <section className="data-panel" aria-label={text("产品列表", "Product list")} aria-busy={products.isFetching}>
        <ListToolbar
          keyword={keyword}
          status={status}
          placeholder={text("按产品名称搜索", "Search product names")}
          createLabel={text("新建产品", "New product")}
          statusOptions={[{ value: "active", label: text("启用", "Active") }, { value: "archived", label: text("已归档", "Archived") }]}
          onCreate={openCreateProduct}
          onApply={(filters) => { setKeyword(filters.keyword); setStatus(filters.status as StatusFilter); setPage(1); }}
        />
        <ListState
          loading={products.isPending}
          error={products.isError ? apiErrorMessage(products.error) : null}
          empty={Boolean(productResult && productResult.data.length === 0)}
          emptyTitle={keyword || status ? text("没有匹配的产品", "No matching products") : text("还没有产品", "No products yet")}
          emptyDescription={keyword || status ? text("尝试调整搜索词或状态筛选。", "Try changing your search or status filter.") : text("新建产品后，可继续为它维护 SKU 变体。", "Create a product, then add its SKU variants.")}
          onRetry={() => void products.refetch()}
        >
          {productResult && <>
            <div className="table-scroll"><table className="data-table">
              <thead><tr><th>{text("产品", "Product")}</th><th>{text("规格 / 单位", "Specification / Unit")}</th><th>{text("参考价格", "Reference price")}</th><th>{text("状态", "Status")}</th><th><span className="sr-only">{text("操作", "Actions")}</span></th></tr></thead>
              <tbody>{productResult.data.map((product) => (
                <tr key={product.id}>
                  <td><div className="product-name-cell"><button className="product-name-link" type="button" title={text("查看产品详情", "View product details")} onClick={() => setViewingProduct(product)}><strong>{product.name}</strong></button>{product.sku_count > 0 && <span className="sku-count">{product.sku_count} SKU</span>}</div><small>{product.product_code || text("未设置产品编号", "No product code")}</small></td>
                  <td><span>{product.spec || <span className="muted-value">{text("未设置规格", "No specification")}</span>}</span><small>{product.unit || text("未设置单位", "No unit")}</small></td>
                  <td className="price-cell">{formatMoney(product.list_price, product.currency, language)}</td>
                  <td><StatusBadge status={product.status} /></td>
                  <td className="row-actions">
                    <button className="text-action" type="button" onClick={() => setViewingProduct(product)}>{text("详情", "Details")}</button>
                    <button className="text-action" type="button" aria-pressed={selectedProduct?.id === product.id} onClick={() => selectProduct(product)}>SKU · {product.sku_count}</button>
                    <button className="text-action" type="button" onClick={() => openEditProduct(product)}>{text("编辑", "Edit")}</button>
                    {product.status !== "archived" && <button className="text-action danger-text" type="button" onClick={() => { archiveProductMutation.reset(); setArchivingProduct(product); }}>{text("归档", "Archive")}</button>}
                  </td>
                </tr>
              ))}</tbody>
            </table></div>
            <Pagination meta={productResult.meta} onPageChange={setPage} />
          </>}
        </ListState>
      </section>

      <section className={`sku-workspace ${selectedProduct ? "selected" : ""}`} aria-label={text("SKU 管理", "SKU management")}>
        {!selectedProduct ? (
          <div className="sku-placeholder"><strong>{text("选择一个产品管理 SKU", "Select a product to manage its SKUs")}</strong><p>{text("点击产品行右侧的“SKU”操作，进入该产品的二级变体目录。", "Use the “SKU” action on a product row to open its variant catalog.")}</p></div>
        ) : (
          <>
            <header className="sku-workspace-header">
              <div><span className="eyebrow">Selected product</span><h3>{selectedProduct.name} · SKU</h3><p>{selectedProduct.product_code || text("无产品编号", "No product code")} · {text(`价格币种 ${selectedProduct.currency}`, `Price currency ${selectedProduct.currency}`)}</p></div>
              <div className="sku-header-actions">
                <button className="button quiet" type="button" onClick={() => setSelectedProduct(null)}>{text("关闭", "Close")}</button>
                <button
                  className="button"
                  type="button"
                  disabled={selectedProduct.status === "archived"}
                  title={selectedProduct.status === "archived" ? text("请先将产品恢复为启用状态", "Restore the product to active first") : undefined}
                  onClick={openBatchCreateSku}
                >
                  {text("批量配码", "Batch variants")}
                </button>
                <button
                  className="button primary"
                  type="button"
                  disabled={selectedProduct.status === "archived"}
                  title={selectedProduct.status === "archived" ? text("请先将产品恢复为启用状态", "Restore the product to active first") : undefined}
                  onClick={openCreateSku}
                >
                  {text("＋ 新建 SKU", "+ New SKU")}
                </button>
              </div>
            </header>
            {batchNotice?.productId === selectedProduct.id && (
              <section className="sku-batch-result" role="status" aria-live="polite">
                <div className="sku-batch-result-summary">
                  <div>
                    <span className="eyebrow">Batch result</span>
                    <strong>{text(`批量配码完成：已创建 ${batchNotice.created.length} 个 SKU，跳过 ${batchNotice.skipped.length} 个值。`, `Batch complete: created ${batchNotice.created.length} SKUs and skipped ${batchNotice.skipped.length} values.`)}</strong>
                  </div>
                  <button className="notice-close" type="button" aria-label={text("关闭批量配码结果", "Dismiss batch result")} onClick={() => setBatchNotice(null)}>×</button>
                </div>
                {batchNotice.created.length > 0 && <div className="sku-batch-result-group"><b>{text("已创建", "Created")}</b><div>{batchNotice.created.map((created) => <span key={created.id}>{batchSkuLabel(created, batchNotice.dimension)}</span>)}</div></div>}
                {batchNotice.skipped.length > 0 && <div className="sku-batch-result-group skipped"><b>{text("已跳过", "Skipped")}</b><div>{batchNotice.skipped.map((value, index) => <span key={`${value}:${index}`}>{value}</span>)}</div></div>}
              </section>
            )}
            <div className="sku-toolbar">
              <form className="sku-filter" role="search" onSubmit={(event) => { event.preventDefault(); setSkuCode(skuCodeDraft.trim()); setSkuPage(1); }}>
                <label className="sr-only" htmlFor="sku-code-filter">{text("精确 SKU 编码", "Exact SKU code")}</label>
                <input id="sku-code-filter" value={skuCodeDraft} placeholder={text("精确 SKU 编码", "Exact SKU code")} onChange={(event) => setSkuCodeDraft(event.target.value)} />
                <label className="sr-only" htmlFor="sku-status-filter">{text("SKU 状态", "SKU status")}</label>
                <select id="sku-status-filter" value={skuStatus} onChange={(event) => { setSkuStatus(event.target.value as StatusFilter); setSkuPage(1); }}><option value="">{text("全部状态", "All statuses")}</option><option value="active">{text("启用", "Active")}</option><option value="archived">{text("已归档", "Archived")}</option></select>
                <button className="button compact" type="submit">{text("查询", "Search")}</button>
                {(skuCode || skuStatus) && <button className="button compact quiet" type="button" onClick={() => { setSkuCode(""); setSkuCodeDraft(""); setSkuStatus(""); setSkuPage(1); }}>{text("清除", "Clear")}</button>}
              </form>
              <span className="eyebrow">Exact code filter</span>
            </div>
            <ListState
              loading={skus.isPending}
              error={skus.isError ? apiErrorMessage(skus.error) : null}
              empty={Boolean(skuResult && skuResult.data.length === 0)}
              emptyTitle={skuCode || skuStatus ? text("没有匹配的 SKU", "No matching SKUs") : text("该产品还没有 SKU", "This product has no SKUs yet")}
              emptyDescription={skuCode || skuStatus ? text("检查精确编码或调整状态筛选。", "Check the exact code or change the status filter.") : text("如果产品有颜色、尺码等变体，可从这里创建第一条 SKU。", "Create the first SKU here if this product has color, size, or other variants.")}
              onRetry={() => void skus.refetch()}
            >
              {skuResult && <>
                <div className="table-scroll"><table className="data-table">
                  <thead><tr><th>{text("SKU 编码", "SKU code")}</th><th>{text("规格属性", "Variant attributes")}</th><th>{text("变体价格", "Variant price")}</th><th>{text("状态", "Status")}</th><th><span className="sr-only">{text("操作", "Actions")}</span></th></tr></thead>
                  <tbody>{skuResult.data.map((sku) => (
                    <tr key={sku.id}>
                      <td className="mono-cell">{sku.sku_code || <span className="muted-value">{text("无编码", "No code")}</span>}</td>
                      <td><AttributeSummary attributes={sku.variant_attrs} /></td>
                      <td className="price-cell">{sku.list_price == null ? <span className="muted-value">{text("继承产品价格", "Inherits product price")}</span> : formatMoney(sku.list_price, selectedProduct.currency, language)}</td>
                      <td><StatusBadge status={sku.status} /></td>
                      <td className="row-actions"><button className="text-action" type="button" onClick={() => openEditSku(sku)}>{text("编辑", "Edit")}</button>{sku.status !== "archived" && <button className="text-action danger-text" type="button" onClick={() => { archiveSkuMutation.reset(); setArchivingSku(sku); }}>{text("归档", "Archive")}</button>}</td>
                    </tr>
                  ))}</tbody>
                </table></div>
                <Pagination meta={skuResult.meta} onPageChange={setSkuPage} />
              </>}
            </ListState>
          </>
        )}
      </section>

      {viewingProduct && (
        <ProductDetailPanel
          product={viewingProduct}
          onClose={() => setViewingProduct(null)}
          onEdit={(product) => { setViewingProduct(null); openEditProduct(product); }}
        />
      )}

      <Drawer
        open={editingProduct !== undefined}
        title={editingProduct ? text("编辑产品", "Edit product") : text("新建产品", "New product")}
        description={editingProduct ? text(`更新 ${editingProduct.name} 的产品级信息。`, `Update product-level information for ${editingProduct.name}.`) : text("建立产品目录项，之后可继续添加 SKU。", "Create a product catalog entry, then add SKUs.")}
        submitLabel={editingProduct ? text("保存更改", "Save changes") : text("创建产品", "Create product")}
        busy={saveProduct.isPending}
        error={productValidation || (saveProduct.isError ? apiErrorMessage(saveProduct.error) : null)}
        onClose={() => !saveProduct.isPending && setEditingProduct(undefined)}
        onSubmit={submitProduct}
      >
        <div className="field-grid">
          <div className="field span-2"><label htmlFor="product-name">{text("产品名称", "Product name")} <b>*</b></label><input id="product-name" maxLength={200} required value={productForm.name} onChange={(event) => setProductForm({ ...productForm, name: event.target.value })} /></div>
          <div className="field"><label htmlFor="product-code">{text("产品编号", "Product code")}</label><input id="product-code" maxLength={64} value={productForm.code} onChange={(event) => setProductForm({ ...productForm, code: event.target.value })} /></div>
          <div className="field"><label htmlFor="product-status">{text("状态", "Status")}</label><select id="product-status" value={productForm.status} onChange={(event) => setProductForm({ ...productForm, status: event.target.value as ActiveStatus })}><option value="active">{text("启用", "Active")}</option><option value="archived">{text("已归档", "Archived")}</option></select></div>
          <div className="field span-2"><label htmlFor="product-spec">{text("产品规格", "Product specification")}</label><input id="product-spec" maxLength={200} value={productForm.spec} onChange={(event) => setProductForm({ ...productForm, spec: event.target.value })} /></div>
          <div className="field"><label htmlFor="product-unit">{text("计量单位", "Unit of measure")}</label><input id="product-unit" maxLength={50} placeholder={text("件、台、箱", "item, unit, box")} value={productForm.unit} onChange={(event) => setProductForm({ ...productForm, unit: event.target.value })} /></div>
          <div className="field"><label htmlFor="product-currency">{text("币种", "Currency")} <b>*</b></label><input id="product-currency" className="currency-input" maxLength={3} required value={productForm.currency} onChange={(event) => setProductForm({ ...productForm, currency: event.target.value.toUpperCase() })} /></div>
          <div className="field span-2"><label htmlFor="product-price">{text("参考价格", "Reference price")}</label><input id="product-price" inputMode="decimal" placeholder="0.00" value={productForm.price} onChange={(event) => setProductForm({ ...productForm, price: event.target.value })} /><small>{text("用于偏差检查，不作为硬性采购上限。", "Used for variance checks, not as a hard purchasing limit.")}</small></div>
        </div>
      </Drawer>

      <Drawer
        open={editingSku !== undefined}
        title={editingSku ? text("编辑 SKU", "Edit SKU") : text("新建 SKU", "New SKU")}
        description={text(`${selectedProduct?.name ?? "当前产品"}的可交易变体。`, `Sellable variant of ${selectedProduct?.name ?? "the current product"}.`)}
        submitLabel={editingSku ? text("保存更改", "Save changes") : text("创建 SKU", "Create SKU")}
        busy={saveSku.isPending}
        error={skuValidation || (saveSku.isError ? apiErrorMessage(saveSku.error) : null)}
        onClose={() => !saveSku.isPending && setEditingSku(undefined)}
        onSubmit={submitSku}
      >
        <div className="field-grid">
          <div className="field"><label htmlFor="sku-code">{text("SKU 编码", "SKU code")}</label><input id="sku-code" maxLength={64} value={skuForm.code} onChange={(event) => setSkuForm({ ...skuForm, code: event.target.value })} /></div>
          <div className="field"><label htmlFor="sku-status">{text("状态", "Status")}</label><select id="sku-status" value={skuForm.status} onChange={(event) => setSkuForm({ ...skuForm, status: event.target.value as ActiveStatus })}><option value="active">{text("启用", "Active")}</option><option value="archived">{text("已归档", "Archived")}</option></select></div>
          <div className="field span-2"><VariantAttributesEditor rows={skuForm.attributes} onChange={(attributes) => setSkuForm({ ...skuForm, attributes })} /></div>
          <div className="field"><label htmlFor="sku-price">{text("变体价格", "Variant price")}</label><input id="sku-price" inputMode="decimal" placeholder={text("留空则继承产品价格", "Leave blank to inherit the product price")} value={skuForm.price} onChange={(event) => setSkuForm({ ...skuForm, price: event.target.value })} /></div>
          <div className="field"><label>{text("价格币种", "Price currency")}</label><div className="inherited-currency">{selectedProduct?.currency ?? "CNY"} · {text("继承产品", "Inherited from product")}</div></div>
        </div>
      </Drawer>

      <Drawer
        open={batchOpen}
        title={text(`批量配码 · ${selectedProduct?.name ?? "当前产品"}`, `Batch variants · ${selectedProduct?.name ?? "Current product"}`)}
        description={text("输入一个规格维度和一组值，系统会为尚不存在的值创建 SKU，并跳过重复规格。", "Enter a variant dimension and its values. The system creates missing SKUs and skips duplicate variants.")}
        submitLabel={text("批量创建 SKU", "Create SKUs in batch")}
        busy={batchCreateSku.isPending}
        error={batchValidation || (batchCreateSku.isError ? apiErrorMessage(batchCreateSku.error) : null)}
        onClose={() => { if (!batchCreateSku.isPending) setBatchOpen(false); }}
        onSubmit={submitBatchSku}
      >
        <div className="field-grid batch-sku-fields">
          <div className="field span-2"><label htmlFor="batch-sku-dimension">{text("配码维度", "Variant dimension")} <b>*</b></label><input id="batch-sku-dimension" required maxLength={50} placeholder={text("尺码", "Size")} value={batchForm.dimension} onChange={(event) => setBatchForm({ ...batchForm, dimension: event.target.value })} /><small>{text("每次批量处理一个维度，例如尺码、颜色或容量。", "Process one dimension at a time, such as size, color, or capacity.")}</small></div>
          <div className="field span-2"><label htmlFor="batch-sku-values">{text("规格值", "Variant values")} <b>*</b></label><textarea id="batch-sku-values" required rows={6} placeholder="S, M, L, XL" value={batchForm.values} onChange={(event) => setBatchForm({ ...batchForm, values: event.target.value })} /><small>{text("可使用逗号、空格、分号、斜杠或换行分隔；已有相同规格的值会被跳过。", "Separate values with commas, spaces, semicolons, slashes, or line breaks. Existing variants are skipped.")}</small></div>
          <div className="field"><label htmlFor="batch-sku-price">{text("统一变体价格", "Shared variant price")}</label><input id="batch-sku-price" inputMode="decimal" placeholder={text("留空则不设置变体价格", "Leave blank to omit a variant price")} value={batchForm.price} onChange={(event) => setBatchForm({ ...batchForm, price: event.target.value })} /></div>
          <div className="field"><label>{text("价格币种", "Price currency")}</label><div className="inherited-currency">{selectedProduct?.currency ?? "CNY"} · {text("仅用于本批次价格", "Used only for this batch")}</div></div>
        </div>
      </Drawer>

      <ConfirmDialog
        open={Boolean(archivingProduct)}
        title={text(`归档“${archivingProduct?.name ?? ""}”？`, `Archive “${archivingProduct?.name ?? ""}”?`)}
        description={text("归档不会删除历史采购引用；该产品不再作为启用目录项，已有 SKU 仍会保留。", "Archiving keeps historical purchasing references and existing SKUs, but the product will no longer be active.")}
        busy={archiveProductMutation.isPending}
        error={archiveProductMutation.isError ? apiErrorMessage(archiveProductMutation.error) : null}
        onCancel={() => !archiveProductMutation.isPending && setArchivingProduct(null)}
        onConfirm={() => archivingProduct && archiveProductMutation.mutate(archivingProduct.id)}
      />
      <ConfirmDialog
        open={Boolean(archivingSku)}
        title={text(`归档 SKU“${archivingSku?.sku_code || "无编码变体"}”？`, `Archive SKU “${archivingSku?.sku_code || "variant without a code"}”?`)}
        description={text("归档后保留历史引用，但新采购申请不应再选择该 SKU。", "Archiving keeps historical references, but new purchase requests should no longer select this SKU.")}
        busy={archiveSkuMutation.isPending}
        error={archiveSkuMutation.isError ? apiErrorMessage(archiveSkuMutation.error) : null}
        onCancel={() => !archiveSkuMutation.isPending && setArchivingSku(null)}
        onConfirm={() => archivingSku && archiveSkuMutation.mutate(archivingSku.id)}
      />
    </div>
  );
}
