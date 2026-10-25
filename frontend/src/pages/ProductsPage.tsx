import { zhCN } from "../locales/zh-CN/console";
import { useRecordNotice } from "../components/master-data/RecordNotice";
import { useListFilters } from "../components/master-data/useListFilters";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState, type FormEvent } from "react";

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

type ProductType = "finished_good" | "raw_material" | "semi_finished" | "service";

type ProductForm = {
  name: string;
  code: string;
  spec: string;
  unit: string;
  price: string;
  currency: string;
  product_type: ProductType;
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
  product_type: "finished_good",
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
    product_type: product.product_type,
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
    return { value: null, error: text(zhCN.pagesProductsPage.pricesCanHaveAtMostTwoDecimalPlaces, "Prices can have at most two decimal places.") };
  }
  const value = Number(normalized);
  if (!Number.isFinite(value) || value < 0 || value > MAX_PRICE) {
    return { value: null, error: text(zhCN.pagesProductsPage.priceMustBeBetween0And(`${MAX_PRICE.toLocaleString()}`), `Price must be between 0 and ${MAX_PRICE.toLocaleString()}.`) };
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
      return { value: {}, error: text(zhCN.pagesProductsPage.everyVariantAttributeRowRequiresBothANameAnd, "Every variant attribute row requires both a name and a value.") };
    }
    if (Object.prototype.hasOwnProperty.call(value, key)) {
      return { value: {}, error: text(zhCN.pagesProductsPage.variantAttributeIsDuplicatedMergeItBeforeSaving(`${key}`), `Variant attribute “${key}” is duplicated. Merge it before saving.`) };
    }
    if (row.valueType === "json") {
      try {
        value[key] = JSON.parse(attributeValue) as unknown;
      } catch {
        return { value: {}, error: text(zhCN.pagesProductsPage.variantAttributeContainsStructuredContentKeepTheOriginalFormat(`${key}`), `Variant attribute “${key}” contains structured content. Keep the original format.`) };
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
  if (entries.length === 0) return <span className="muted-value">{text(zhCN.pagesProductsPage.noVariants, "No variants")}</span>;
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
  const skuPanelRef = useRef<HTMLElement>(null);
  const { notice, notify } = useRecordNotice();
  const { keyword, status, page, setPage, applyFilters } = useListFilters<StatusFilter>(["active", "archived"]);
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
  const [batchForm, setBatchForm] = useState<BatchSkuForm>(() => emptyBatchSkuForm(text(zhCN.pagesProductsPage.size, "Size")));
  const [batchValidation, setBatchValidation] = useState<string | null>(null);
  const [batchNotice, setBatchNotice] = useState<BatchSkuNotice | null>(null);

  const products = useQuery({
    queryKey: ["master-data", "products", { keyword, status, page }],
    queryFn: () => listProducts({ page, size: PAGE_SIZE, keyword: keyword || undefined, status: status || "all" }),
    placeholderData: keepPreviousData,
  });

  const skus = useQuery({
    queryKey: ["master-data", "product-skus", selectedProduct?.id, { skuCode, skuStatus, skuPage }],
    queryFn: () => listProductSkus({
      product_id: selectedProduct!.id,
      page: skuPage,
      size: PAGE_SIZE,
      sku_code: skuCode || undefined,
      status: skuStatus || "all",
    }),
    enabled: selectedProduct !== null,
  });

  useEffect(() => {
    if (!selectedProduct) return;
    skuPanelRef.current?.focus({ preventScroll: true });
    skuPanelRef.current?.scrollIntoView?.({ block: "start", behavior: "instant" });
  }, [selectedProduct?.id]);

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
      notify(variables.id ? "saved" : "created");
      if (!variables.id) setPage(1);
      setSelectedProduct((current: Product | null) => current?.id === saved.id ? saved : current);
      await queryClient.invalidateQueries({ queryKey: ["master-data", "products"] });
    },
  });

  const archiveProductMutation = useMutation({
    mutationFn: (id: string) => archiveProduct(id),
    onSuccess: async (_, id) => {
      setArchivingProduct(null);
      notify("archived");
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
      notify(variables.mode === "create" ? "created" : "saved");
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
      notify("archived");
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
      setProductValidation(text(zhCN.pagesProductsPage.productNameIsRequired, "Product name is required."));
      return;
    }
    if (!/^[A-Z]{3}$/.test(currency)) {
      setProductValidation(text(zhCN.pagesProductsPage.currencyMustBeAThreeLetterISOCodeSuch, "Currency must be a three-letter ISO code, such as CNY or USD."));
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
        product_type: productForm.product_type,
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
    setBatchForm(emptyBatchSkuForm(text(zhCN.pagesProductsPage.size, "Size")));
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
      setSkuValidation(text(zhCN.pagesProductsPage.enterASKUCodeOrAddAtLeastOne, "Enter a SKU code or add at least one variant attribute."));
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
      setBatchValidation(text(zhCN.pagesProductsPage.enterAVariantDimensionSuchAsSizeOrColor, "Enter a variant dimension, such as size or color."));
      return;
    }
    if (values.length === 0) {
      setBatchValidation(text(zhCN.pagesProductsPage.enterAtLeastOneVariantValue, "Enter at least one variant value."));
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
        <div><span className="eyebrow">Product catalog</span><h2>{text(zhCN.pagesProductsPage.productsAndSKUs, "Products and SKUs")}</h2><p>{text(zhCN.pagesProductsPage.maintainProductLevelInformationThenCreateSKUsForColors, "Maintain product-level information, then create SKUs for colors, sizes, or other sellable variants.")}</p></div>
      </header>
      {notice}

      <section className="data-panel" aria-label={text(zhCN.pagesProductsPage.productList, "Product list")} aria-busy={products.isFetching}>
        <ListToolbar
          keyword={keyword}
          status={status}
          placeholder={text(zhCN.pagesProductsPage.searchProductNames, "Search product names")}
          createLabel={text(zhCN.pagesProductsPage.newProduct, "New product")}
          statusOptions={[{ value: "active", label: text(zhCN.pagesProductsPage.active, "Active") }, { value: "archived", label: text(zhCN.pagesProductsPage.archived, "Archived") }]}
          onCreate={openCreateProduct}
          onApply={applyFilters}
        />
        <ListState
          loading={products.isPending}
          error={products.isError ? apiErrorMessage(products.error) : null}
          empty={Boolean(productResult && productResult.data.length === 0)}
          emptyTitle={keyword || status ? text(zhCN.pagesProductsPage.noMatchingProducts, "No matching products") : text(zhCN.pagesProductsPage.noProductsYet, "No products yet")}
          emptyDescription={keyword || status ? text(zhCN.pagesProductsPage.tryChangingYourSearchOrStatusFilter, "Try changing your search or status filter.") : text(zhCN.pagesProductsPage.createAProductThenAddItsSKUVariants, "Create a product, then add its SKU variants.")}
          onRetry={() => void products.refetch()}
        >
          {productResult && <>
            <div className="table-scroll"><table className="data-table">
              <thead><tr><th>{text(zhCN.pagesProductsPage.product, "Product")}</th><th>{text(zhCN.pagesProductsPage.specificationUnit, "Specification / Unit")}</th><th>{text(zhCN.pagesProductsPage.referencePrice, "Reference price")}</th><th>{text(zhCN.pagesProductsPage.status, "Status")}</th><th><span className="sr-only">{text(zhCN.pagesProductsPage.actions, "Actions")}</span></th></tr></thead>
              <tbody>{productResult.data.map((product) => (
                <tr key={product.id}>
                  <td><div className="product-name-cell"><button className="product-name-link" type="button" title={text(zhCN.pagesProductsPage.viewProductDetails, "View product details")} onClick={() => setViewingProduct(product)}><strong>{product.name}</strong></button>{product.sku_count > 0 && <span className="sku-count">{product.sku_count} SKU</span>}</div><small>{product.product_code || text(zhCN.pagesProductsPage.noProductCode, "No product code")}</small></td>
                  <td><span>{product.spec || <span className="muted-value">{text(zhCN.pagesProductsPage.noVariants, "No specification")}</span>}</span><small>{product.unit || text(zhCN.pagesProductsPage.noUnit, "No unit")}</small></td>
                  <td className="price-cell">{formatMoney(product.list_price, product.currency, language)}</td>
                  <td><StatusBadge status={product.status} /></td>
                  <td className="row-actions">
                    <button className="text-action" type="button" onClick={() => setViewingProduct(product)}>{text(zhCN.pagesProductsPage.details, "Details")}</button>
                    <button className="text-action" type="button" aria-pressed={selectedProduct?.id === product.id} onClick={() => selectProduct(product)}>SKU · {product.sku_count}</button>
                    <button className="text-action" type="button" onClick={() => openEditProduct(product)}>{text(zhCN.pagesProductsPage.edit, "Edit")}</button>
                    {product.status !== "archived" && <button className="text-action danger-text" type="button" onClick={() => { archiveProductMutation.reset(); setArchivingProduct(product); }}>{text(zhCN.pagesProductsPage.archive, "Archive")}</button>}
                  </td>
                </tr>
              ))}</tbody>
            </table></div>
            <Pagination meta={productResult.meta} onPageChange={setPage} />
          </>}
        </ListState>
      </section>

      <section ref={skuPanelRef} tabIndex={-1} hidden={!selectedProduct} className={`sku-workspace ${selectedProduct ? "selected" : ""}`} aria-label={text(zhCN.pagesProductsPage.sKUManagement, "SKU management")}>
        {!selectedProduct ? (
          <div className="sku-placeholder"><strong>{text(zhCN.pagesProductsPage.selectAProductToManageItsSKUs, "Select a product to manage its SKUs")}</strong><p>{text(zhCN.pagesProductsPage.useTheSKUActionOnAProductRowTo, "Use the “SKU” action on a product row to open its variant catalog.")}</p></div>
        ) : (
          <>
            <header className="sku-workspace-header">
              <div><span className="eyebrow">{text(zhCN.pagesProductsPage.selectedProduct, "Selected product")}</span><h3>{selectedProduct.name} · SKU</h3><p>{selectedProduct.product_code || text(zhCN.pagesProductsPage.noProductCode2, "No product code")} · {text(zhCN.pagesProductsPage.priceCurrency2(`${selectedProduct.currency}`), `Price currency ${selectedProduct.currency}`)}</p></div>
              <div className="sku-header-actions">
                <button className="button quiet" type="button" onClick={() => setSelectedProduct(null)}>{text(zhCN.pagesProductsPage.close, "Close")}</button>
                <button
                  className="button"
                  type="button"
                  disabled={selectedProduct.status === "archived"}
                  title={selectedProduct.status === "archived" ? text(zhCN.pagesProductsPage.restoreTheProductToActiveFirst, "Restore the product to active first") : undefined}
                  onClick={openBatchCreateSku}
                >
                  {text(zhCN.pagesProductsPage.batchVariants, "Batch variants")}
                </button>
                <button
                  className="button primary"
                  type="button"
                  disabled={selectedProduct.status === "archived"}
                  title={selectedProduct.status === "archived" ? text(zhCN.pagesProductsPage.restoreTheProductToActiveFirst, "Restore the product to active first") : undefined}
                  onClick={openCreateSku}
                >
                  {text(zhCN.pagesProductsPage.newSKU, "+ New SKU")}
                </button>
              </div>
            </header>
            {batchNotice?.productId === selectedProduct.id && (
              <section className="sku-batch-result" role="status" aria-live="polite">
                <div className="sku-batch-result-summary">
                  <div>
                    <span className="eyebrow">{text(zhCN.pagesProductsPage.batchResult, "Batch result")}</span>
                    <strong>{text(zhCN.pagesProductsPage.batchCompleteCreatedSKUsAndSkippedValues(`${batchNotice.created.length}`, `${batchNotice.skipped.length}`), `Batch complete: created ${batchNotice.created.length} SKUs and skipped ${batchNotice.skipped.length} values.`)}</strong>
                  </div>
                  <button className="notice-close" type="button" aria-label={text(zhCN.pagesProductsPage.dismissBatchResult, "Dismiss batch result")} onClick={() => setBatchNotice(null)}>×</button>
                </div>
                {batchNotice.created.length > 0 && <div className="sku-batch-result-group"><b>{text(zhCN.pagesProductsPage.created, "Created")}</b><div>{batchNotice.created.map((created) => <span key={created.id}>{batchSkuLabel(created, batchNotice.dimension)}</span>)}</div></div>}
                {batchNotice.skipped.length > 0 && <div className="sku-batch-result-group skipped"><b>{text(zhCN.pagesProductsPage.skipped, "Skipped")}</b><div>{batchNotice.skipped.map((value, index) => <span key={`${value}:${index}`}>{value}</span>)}</div></div>}
              </section>
            )}
            <div className="sku-toolbar">
              <form className="sku-filter" role="search" onSubmit={(event) => { event.preventDefault(); setSkuCode(skuCodeDraft.trim()); setSkuPage(1); }}>
                <label className="sr-only" htmlFor="sku-code-filter">{text(zhCN.pagesProductsPage.exactSKUCode, "Exact SKU code")}</label>
                <input id="sku-code-filter" value={skuCodeDraft} placeholder={text(zhCN.pagesProductsPage.exactSKUCode, "Exact SKU code")} onChange={(event) => setSkuCodeDraft(event.target.value)} />
                <label className="sr-only" htmlFor="sku-status-filter">{text(zhCN.pagesProductsPage.sKUStatus, "SKU status")}</label>
                <select id="sku-status-filter" value={skuStatus} onChange={(event) => { setSkuStatus(event.target.value as StatusFilter); setSkuPage(1); }}><option value="">{text(zhCN.pagesProductsPage.allStatuses, "All statuses")}</option><option value="active">{text(zhCN.pagesProductsPage.active, "Active")}</option><option value="archived">{text(zhCN.pagesProductsPage.archived, "Archived")}</option></select>
                <button className="button compact" type="submit">{text(zhCN.pagesProductsPage.search, "Search")}</button>
                {(skuCode || skuStatus) && <button className="button compact quiet" type="button" onClick={() => { setSkuCode(""); setSkuCodeDraft(""); setSkuStatus(""); setSkuPage(1); }}>{text(zhCN.pagesProductsPage.clear, "Clear")}</button>}
              </form>

            </div>
            <ListState
              loading={skus.isPending}
              error={skus.isError ? apiErrorMessage(skus.error) : null}
              empty={Boolean(skuResult && skuResult.data.length === 0)}
              emptyTitle={skuCode || skuStatus ? text(zhCN.pagesProductsPage.noMatchingSKUs, "No matching SKUs") : text(zhCN.pagesProductsPage.thisProductHasNoSKUsYet, "This product has no SKUs yet")}
              emptyDescription={skuCode || skuStatus ? text(zhCN.pagesProductsPage.checkTheExactCodeOrChangeTheStatusFilter, "Check the exact code or change the status filter.") : text(zhCN.pagesProductsPage.createTheFirstSKUHereIfThisProductHas, "Create the first SKU here if this product has color, size, or other variants.")}
              onRetry={() => void skus.refetch()}
            >
              {skuResult && <>
                <div className="table-scroll"><table className="data-table">
                  <thead><tr><th>{text(zhCN.pagesProductsPage.sKUCode, "SKU code")}</th><th>{text(zhCN.pagesProductsPage.variantAttributes, "Variant attributes")}</th><th>{text(zhCN.pagesProductsPage.variantPrice, "Variant price")}</th><th>{text(zhCN.pagesProductsPage.status, "Status")}</th><th><span className="sr-only">{text(zhCN.pagesProductsPage.actions, "Actions")}</span></th></tr></thead>
                  <tbody>{skuResult.data.map((sku) => (
                    <tr key={sku.id}>
                      <td className="mono-cell">{sku.sku_code || <span className="muted-value">{text(zhCN.pagesProductsPage.noCode, "No code")}</span>}</td>
                      <td><AttributeSummary attributes={sku.variant_attrs} /></td>
                      <td className="price-cell">{sku.list_price == null ? <span className="muted-value">{text(zhCN.pagesProductsPage.inheritsProductPrice, "Inherits product price")}</span> : formatMoney(sku.list_price, selectedProduct.currency, language)}</td>
                      <td><StatusBadge status={sku.status} /></td>
                      <td className="row-actions"><button className="text-action" type="button" onClick={() => openEditSku(sku)}>{text(zhCN.pagesProductsPage.edit, "Edit")}</button>{sku.status !== "archived" && <button className="text-action danger-text" type="button" onClick={() => { archiveSkuMutation.reset(); setArchivingSku(sku); }}>{text(zhCN.pagesProductsPage.archive, "Archive")}</button>}</td>
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
        title={editingProduct ? text(zhCN.pagesProductsPage.editProduct, "Edit product") : text(zhCN.pagesProductsPage.newProduct, "New product")}
        description={editingProduct ? text(zhCN.pagesProductsPage.updateProductLevelInformationFor(`${editingProduct.name}`), `Update product-level information for ${editingProduct.name}.`) : text(zhCN.pagesProductsPage.createAProductCatalogEntryThenAddSKUs, "Create a product catalog entry, then add SKUs.")}
        submitLabel={editingProduct ? text(zhCN.pagesProductsPage.saveChanges, "Save changes") : text(zhCN.pagesProductsPage.createProduct, "Create product")}
        busy={saveProduct.isPending}
        error={productValidation || (saveProduct.isError ? apiErrorMessage(saveProduct.error) : null)}
        onClose={() => !saveProduct.isPending && setEditingProduct(undefined)}
        onSubmit={submitProduct}
      >
        <div className="field-grid">
          <div className="field span-2"><label htmlFor="product-name">{text(zhCN.pagesProductsPage.productName, "Product name")} <b>*</b></label><input id="product-name" maxLength={200} required value={productForm.name} onChange={(event) => setProductForm({ ...productForm, name: event.target.value })} /></div>
          <div className="field"><label htmlFor="product-code">{text(zhCN.pagesProductsPage.productCode, "Product code")}</label><input id="product-code" maxLength={64} value={productForm.code} onChange={(event) => setProductForm({ ...productForm, code: event.target.value })} /></div>
          <div className="field"><label htmlFor="product-status">{text(zhCN.pagesProductsPage.status, "Status")}</label><select id="product-status" value={productForm.status} onChange={(event) => setProductForm({ ...productForm, status: event.target.value as ActiveStatus })}><option value="active">{text(zhCN.pagesProductsPage.active, "Active")}</option><option value="archived">{text(zhCN.pagesProductsPage.archived, "Archived")}</option></select></div>
          <div className="field span-2"><label htmlFor="product-spec">{text(zhCN.pagesProductsPage.productSpecification, "Product specification")}</label><input id="product-spec" maxLength={200} value={productForm.spec} onChange={(event) => setProductForm({ ...productForm, spec: event.target.value })} /></div>
          <div className="field"><label htmlFor="product-unit">{text(zhCN.pagesProductsPage.unitOfMeasure, "Unit of measure")}</label><input id="product-unit" maxLength={50} placeholder={text(zhCN.pagesProductsPage.itemUnitBox, "item, unit, box")} value={productForm.unit} onChange={(event) => setProductForm({ ...productForm, unit: event.target.value })} /></div>
          <div className="field"><label htmlFor="product-currency">{text(zhCN.pagesProductsPage.currency, "Currency")} <b>*</b></label><input id="product-currency" className="currency-input" maxLength={3} required value={productForm.currency} onChange={(event) => setProductForm({ ...productForm, currency: event.target.value.toUpperCase() })} /></div>
          <div className="field"><label htmlFor="product-type">{text(zhCN.pagesProductsPage.productType, "Product type")}</label><select id="product-type" value={productForm.product_type} onChange={(event) => setProductForm({ ...productForm, product_type: event.target.value as ProductType })}>
            <option value="finished_good">{text(zhCN.pagesProductsPage.finishedGood, "Finished good")}</option>
            <option value="semi_finished">{text(zhCN.pagesProductsPage.semiFinished, "Semi-finished")}</option>
            <option value="raw_material">{text(zhCN.pagesProductsPage.rawMaterial, "Raw material")}</option>
            <option value="service">{text(zhCN.pagesProductsPage.service, "Service")}</option>
          </select></div>
          <div className="field span-2"><label htmlFor="product-price">{text(zhCN.pagesProductsPage.referencePrice, "Reference price")}</label><input id="product-price" inputMode="decimal" placeholder="0.00" value={productForm.price} onChange={(event) => setProductForm({ ...productForm, price: event.target.value })} /><small>{text(zhCN.pagesProductsPage.usedForVarianceChecksNotAsAHardPurchasing, "Used for variance checks, not as a hard purchasing limit.")}</small></div>
        </div>
      </Drawer>

      <Drawer
        open={editingSku !== undefined}
        title={editingSku ? text(zhCN.pagesProductsPage.editSKU, "Edit SKU") : text(zhCN.pagesProductsPage.newSKU2, "New SKU")}
        description={text(zhCN.pagesProductsPage.sellableVariantOf(`${selectedProduct?.name ?? zhCN.pagesProductsPage.selectedProduct}`), `Sellable variant of ${selectedProduct?.name ?? "the current product"}.`)}
        submitLabel={editingSku ? text(zhCN.pagesProductsPage.saveChanges, "Save changes") : text(zhCN.pagesProductsPage.createSKU, "Create SKU")}
        busy={saveSku.isPending}
        error={skuValidation || (saveSku.isError ? apiErrorMessage(saveSku.error) : null)}
        onClose={() => !saveSku.isPending && setEditingSku(undefined)}
        onSubmit={submitSku}
      >
        <div className="field-grid">
          <div className="field"><label htmlFor="sku-code">{text(zhCN.pagesProductsPage.sKUCode, "SKU code")}</label><input id="sku-code" maxLength={64} value={skuForm.code} onChange={(event) => setSkuForm({ ...skuForm, code: event.target.value })} /></div>
          <div className="field"><label htmlFor="sku-status">{text(zhCN.pagesProductsPage.status, "Status")}</label><select id="sku-status" value={skuForm.status} onChange={(event) => setSkuForm({ ...skuForm, status: event.target.value as ActiveStatus })}><option value="active">{text(zhCN.pagesProductsPage.active, "Active")}</option><option value="archived">{text(zhCN.pagesProductsPage.archived, "Archived")}</option></select></div>
          <div className="field span-2"><VariantAttributesEditor rows={skuForm.attributes} onChange={(attributes) => setSkuForm({ ...skuForm, attributes })} /></div>
          <div className="field"><label htmlFor="sku-price">{text(zhCN.pagesProductsPage.variantPrice, "Variant price")}</label><input id="sku-price" inputMode="decimal" placeholder={text(zhCN.pagesProductsPage.leaveBlankToInheritTheProductPrice, "Leave blank to inherit the product price")} value={skuForm.price} onChange={(event) => setSkuForm({ ...skuForm, price: event.target.value })} /></div>
          <div className="field"><label>{text(zhCN.pagesProductsPage.priceCurrency, "Price currency")}</label><div className="inherited-currency">{selectedProduct?.currency ?? "CNY"} · {text(zhCN.pagesProductsPage.inheritedFromProduct, "Inherited from product")}</div></div>
        </div>
      </Drawer>

      <Drawer
        open={batchOpen}
        title={text(zhCN.pagesProductsPage.batchVariants2(`${selectedProduct?.name ?? zhCN.pagesProductsPage.selectedProduct}`), `Batch variants · ${selectedProduct?.name ?? "Current product"}`)}
        description={text(zhCN.pagesProductsPage.enterAVariantDimensionAndItsValuesTheSystem, "Enter a variant dimension and its values. The system creates missing SKUs and skips duplicate variants.")}
        submitLabel={text(zhCN.pagesProductsPage.createSKUsInBatch, "Create SKUs in batch")}
        busy={batchCreateSku.isPending}
        error={batchValidation || (batchCreateSku.isError ? apiErrorMessage(batchCreateSku.error) : null)}
        onClose={() => { if (!batchCreateSku.isPending) setBatchOpen(false); }}
        onSubmit={submitBatchSku}
      >
        <div className="field-grid batch-sku-fields">
          <div className="field span-2"><label htmlFor="batch-sku-dimension">{text(zhCN.pagesProductsPage.variantDimension, "Variant dimension")} <b>*</b></label><input id="batch-sku-dimension" required maxLength={50} placeholder={text(zhCN.pagesProductsPage.size, "Size")} value={batchForm.dimension} onChange={(event) => setBatchForm({ ...batchForm, dimension: event.target.value })} /><small>{text(zhCN.pagesProductsPage.processOneDimensionAtATimeSuchAsSize, "Process one dimension at a time, such as size, color, or capacity.")}</small></div>
          <div className="field span-2"><label htmlFor="batch-sku-values">{text(zhCN.pagesProductsPage.variantValues, "Variant values")} <b>*</b></label><textarea id="batch-sku-values" required rows={6} placeholder="S, M, L, XL" value={batchForm.values} onChange={(event) => setBatchForm({ ...batchForm, values: event.target.value })} /><small>{text(zhCN.pagesProductsPage.separateValuesWithCommasSpacesSemicolonsSlashesOrLine, "Separate values with commas, spaces, semicolons, slashes, or line breaks. Existing variants are skipped.")}</small></div>
          <div className="field"><label htmlFor="batch-sku-price">{text(zhCN.pagesProductsPage.sharedVariantPrice, "Shared variant price")}</label><input id="batch-sku-price" inputMode="decimal" placeholder={text(zhCN.pagesProductsPage.leaveBlankToOmitAVariantPrice, "Leave blank to omit a variant price")} value={batchForm.price} onChange={(event) => setBatchForm({ ...batchForm, price: event.target.value })} /></div>
          <div className="field"><label>{text(zhCN.pagesProductsPage.priceCurrency, "Price currency")}</label><div className="inherited-currency">{selectedProduct?.currency ?? "CNY"} · {text(zhCN.pagesProductsPage.usedOnlyForThisBatch, "Used only for this batch")}</div></div>
        </div>
      </Drawer>

      <ConfirmDialog
        open={Boolean(archivingProduct)}
        title={text(zhCN.pagesProductsPage.archive2(`${archivingProduct?.name ?? ""}`), `Archive “${archivingProduct?.name ?? ""}”?`)}
        description={text(zhCN.pagesProductsPage.archivingKeepsHistoricalPurchasingReferencesAndExistingSKUsBut, "Archiving keeps historical purchasing references and existing SKUs, but the product will no longer be active.")}
        busy={archiveProductMutation.isPending}
        error={archiveProductMutation.isError ? apiErrorMessage(archiveProductMutation.error) : null}
        onCancel={() => !archiveProductMutation.isPending && setArchivingProduct(null)}
        onConfirm={() => archivingProduct && archiveProductMutation.mutate(archivingProduct.id)}
      />
      <ConfirmDialog
        open={Boolean(archivingSku)}
        title={text(zhCN.pagesProductsPage.archiveSKU(`${archivingSku?.sku_code || zhCN.pagesProductsPage.message}`), `Archive SKU “${archivingSku?.sku_code || "variant without a code"}”?`)}
        description={text(zhCN.pagesProductsPage.archivingKeepsHistoricalReferencesButNewPurchaseRequestsShould, "Archiving keeps historical references, but new purchase requests should no longer select this SKU.")}
        busy={archiveSkuMutation.isPending}
        error={archiveSkuMutation.isError ? apiErrorMessage(archiveSkuMutation.error) : null}
        onCancel={() => !archiveSkuMutation.isPending && setArchivingSku(null)}
        onConfirm={() => archivingSku && archiveSkuMutation.mutate(archivingSku.id)}
      />
    </div>
  );
}
