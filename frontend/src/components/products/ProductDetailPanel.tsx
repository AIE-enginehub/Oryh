import { zhCN } from "../../locales/zh-CN/console";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState, type ReactNode } from "react";

import {
  listInventoryItemDetails,
  listInventoryItems,
  listProductImages,
  listProductPrices,
  productImageContentUrl,
  listProductSkus,
  listSupplierProducts,
  type InventoryItemDetailRead,
  type InventoryItemRead,
  type Product,
  type ProductPriceRead,
  type SupplierProductRead,
} from "../../api/client";
import { apiErrorMessage, StatusBadge } from "../master-data/ListState";
import { useI18n } from "../../i18n";

type LocalText = (chinese: string, english: string) => string;

function formatMoney(value: number | null | undefined, currency: string, locale: string): string {
  if (value == null) return "—";
  try {
    return new Intl.NumberFormat(locale, { style: "currency", currency }).format(value);
  } catch {
    return `${currency} ${value.toFixed(2)}`;
  }
}

function formatTimestamp(value: string | null | undefined, locale: string): string {
  if (!value) return "—";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString(locale);
}

function priceTypeLabel(type: ProductPriceRead["price_type"], text: LocalText): string {
  // shipped catalog only — tenant-defined types (via /type-options) show
  // their own name verbatim
  const labels: Record<string, [string, string] | undefined> = {
    list: [zhCN.componentsProductsProductDetailPanel.listPrice, "List"],
    default: [zhCN.componentsProductsProductDetailPanel.message2, "Default"],
    promo: [zhCN.componentsProductsProductDetailPanel.message3, "Promo"],
    wholesale: [zhCN.componentsProductsProductDetailPanel.message4, "Wholesale"],
    competitive: [zhCN.componentsProductsProductDetailPanel.message5, "Competitive"],
    minimum: [zhCN.componentsProductsProductDetailPanel.message6, "Minimum"],
    maximum: [zhCN.componentsProductsProductDetailPanel.message7, "Maximum"],
    cost: [zhCN.componentsProductsProductDetailPanel.message8, "Cost"],
  };
  const entry = labels[type];
  return entry ? text(entry[0], entry[1]) : type;
}

function movementReasonLabel(reason: InventoryItemDetailRead["reason"], text: LocalText): string {
  const labels: Record<InventoryItemDetailRead["reason"], [string, string]> = {
    initial: [zhCN.componentsProductsProductDetailPanel.message9, "Initial"],
    import_initial: [zhCN.componentsProductsProductDetailPanel.message10, "Import initial"],
    import_override: [zhCN.componentsProductsProductDetailPanel.message11, "Import override"],
    received: [zhCN.componentsProductsProductDetailPanel.message12, "Received"],
    issued: [zhCN.componentsProductsProductDetailPanel.message13, "Issued"],
    adjustment: [zhCN.componentsProductsProductDetailPanel.message14, "Adjustment"],
    damaged: [zhCN.componentsProductsProductDetailPanel.message15, "Damaged"],
    returned: [zhCN.componentsProductsProductDetailPanel.message16, "Returned"],
    transfer: [zhCN.componentsProductsProductDetailPanel.message17, "Transfer"],
    reserved: [zhCN.componentsProductsProductDetailPanel.message18, "Reserved"],
    reservation_released: [zhCN.componentsProductsProductDetailPanel.message19, "Hold released"],
    production: [zhCN.componentsProductsProductDetailPanel.message20, "Production receipt"],
    other: [zhCN.componentsProductsProductDetailPanel.message21, "Other"],
  };
  const [chinese, english] = labels[reason];
  return text(chinese, english);
}

function signedQuantity(value: number): string {
  return value > 0 ? `+${value}` : String(value);
}

/** Every value of a jsonb blob, faithfully: scalars inline, structures as
 * formatted JSON — nothing summarized away. */
function JsonValue({ value }: { value: unknown }) {
  if (value == null) return <span className="muted-value">null</span>;
  if (typeof value === "string") return <span>{value}</span>;
  if (typeof value === "number" || typeof value === "boolean") return <code>{String(value)}</code>;
  return <pre className="json-pre">{JSON.stringify(value, null, 2)}</pre>;
}

function MetadataBlock({ metadata }: { metadata: Record<string, unknown> }) {
  const { text } = useI18n();
  const entries = Object.entries(metadata);
  if (entries.length === 0) {
    return <p className="muted-value">{text(zhCN.componentsProductsProductDetailPanel.noAdditionalFields, "No additional fields.")}</p>;
  }
  return (
    <dl className="detail-grid metadata-grid">
      {entries.map(([key, value]) => (
        <div className="detail-field" key={key}>
          <dt>{key}</dt>
          <dd><JsonValue value={value} /></dd>
        </div>
      ))}
    </dl>
  );
}

function MetadataToggle({ metadata }: { metadata: Record<string, unknown> }) {
  const { text } = useI18n();
  if (Object.keys(metadata).length === 0) return <span className="muted-value">—</span>;
  return (
    <details className="metadata-toggle">
      <summary>{text(zhCN.componentsProductsProductDetailPanel.view, "View")}</summary>
      <pre className="json-pre">{JSON.stringify(metadata, null, 2)}</pre>
    </details>
  );
}

function DetailSection({ title, count, children }: { title: string; count?: number; children: ReactNode }) {
  return (
    <section className="detail-section">
      <h4>{title}{count !== undefined && <span className="detail-count">{count}</span>}</h4>
      {children}
    </section>
  );
}

function SectionState({
  loading, error, empty, emptyText, children,
}: { loading: boolean; error: string | null; empty: boolean; emptyText: string; children: ReactNode }) {
  const { text } = useI18n();
  if (loading) return <p className="muted-value">{text(zhCN.componentsProductsProductDetailPanel.loading, "Loading…")}</p>;
  if (error) return <p className="detail-error" role="alert">{error}</p>;
  if (empty) return <p className="muted-value">{emptyText}</p>;
  return <>{children}</>;
}

function InventoryLedger({ item, skuLabel }: { item: InventoryItemRead; skuLabel: string }) {
  const { language, text } = useI18n();
  const [open, setOpen] = useState(false);
  const ledger = useQuery({
    queryKey: ["product-detail", "inventory-ledger", item.id],
    queryFn: () => listInventoryItemDetails({ inventory_item_id: item.id }),
    enabled: open,
  });
  const rows = ledger.data?.data ?? [];
  return (
    <details
      className="inventory-position"
      onToggle={(event) => setOpen((event.target as HTMLDetailsElement).open)}
    >
      <summary>
        <span className="inventory-place">
          {item.facility || text(zhCN.componentsProductsProductDetailPanel.noFacility, "No facility")}
          {item.lot_id && <small>{text(zhCN.componentsProductsProductDetailPanel.lot, "Lot")} {item.lot_id}</small>}
          {item.bin_number && <small>{text(zhCN.componentsProductsProductDetailPanel.bin, "Bin")} {item.bin_number}</small>}
          {skuLabel && <small>SKU {skuLabel}</small>}
        </span>
        <span className="inventory-numbers">
          <b>{item.quantity_on_hand}</b>
          <small>{text(zhCN.componentsProductsProductDetailPanel.aTP, "ATP")} {item.available_to_promise}</small>
          {item.expire_date && <small>{text(zhCN.componentsProductsProductDetailPanel.expires, "Expires")} {item.expire_date}</small>}
          {item.unit_cost != null && <small>{text(zhCN.componentsProductsProductDetailPanel.cost, "Cost")} {formatMoney(item.unit_cost, item.currency, language)}</small>}
          <StatusBadge status={item.status} />
        </span>
      </summary>
      <SectionState
        loading={open && ledger.isPending}
        error={ledger.isError ? apiErrorMessage(ledger.error) : null}
        empty={Boolean(ledger.data) && rows.length === 0}
        emptyText={text(zhCN.componentsProductsProductDetailPanel.noMovementsRecordedForThisItem, "No movements recorded for this item.")}
      >
        <div className="table-scroll">
          <table className="data-table ledger-table">
            <thead><tr>
              <th>{text(zhCN.componentsProductsProductDetailPanel.time, "Time")}</th>
              <th>{text(zhCN.componentsProductsProductDetailPanel.reason, "Reason")}</th>
              <th>{text(zhCN.componentsProductsProductDetailPanel.qtyChange, "Qty change")}</th>
              <th>{text(zhCN.componentsProductsProductDetailPanel.aTPChange, "ATP change")}</th>
              <th>{text(zhCN.componentsProductsProductDetailPanel.description, "Description")}</th>
              <th>{text(zhCN.componentsProductsProductDetailPanel.by, "By")}</th>
            </tr></thead>
            <tbody>
              {rows.map((detail) => (
                <tr key={detail.id}>
                  <td>{formatTimestamp(detail.effective_at, language)}</td>
                  <td><span className={`reason-chip reason-${detail.reason}`}>{movementReasonLabel(detail.reason, text)}</span></td>
                  <td className={`price-cell ${detail.quantity_on_hand_diff < 0 ? "negative" : "positive"}`}>{signedQuantity(detail.quantity_on_hand_diff)}</td>
                  <td className="price-cell">{signedQuantity(detail.available_to_promise_diff)}</td>
                  <td className="ledger-description">{detail.description || "—"}</td>
                  <td>{detail.created_by || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </SectionState>
    </details>
  );
}

export function ProductDetailPanel({ product, onClose, onEdit }: {
  product: Product;
  onClose: () => void;
  onEdit?: (product: Product) => void;
}) {
  const { language, text } = useI18n();
  const panelRef = useRef<HTMLElement>(null);
  const closeRef = useRef(onClose);
  closeRef.current = onClose;

  useEffect(() => {
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    panelRef.current?.querySelector<HTMLElement>("button")?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") closeRef.current();
    };
    document.addEventListener("keydown", onKeyDown);
    document.body.classList.add("modal-open");
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.body.classList.remove("modal-open");
      previous?.focus();
    };
  }, []);

  const images = useQuery({
    queryKey: ["product-detail", "images", product.id],
    queryFn: () => listProductImages({ product_id: product.id, size: 50 }),
  });
  const prices = useQuery({
    queryKey: ["product-detail", "prices", product.id],
    queryFn: () => listProductPrices({ product_id: product.id }),
  });
  const suppliers = useQuery({
    queryKey: ["product-detail", "suppliers", product.id],
    queryFn: () => listSupplierProducts({ product_id: product.id }),
  });
  const inventory = useQuery({
    queryKey: ["product-detail", "inventory", product.id],
    queryFn: () => listInventoryItems({ product_id: product.id }),
  });
  const skus = useQuery({
    queryKey: ["product-detail", "skus", product.id],
    queryFn: () => listProductSkus({ product_id: product.id, size: 200 }),
    enabled: product.has_skus,
  });

  const skuLabelById = new Map<string, string>();
  for (const sku of skus.data?.data ?? []) {
    skuLabelById.set(sku.id, sku.sku_code || Object.values(sku.variant_attrs).map(String).join("/") || sku.id.slice(0, 8));
  }
  const skuLabel = (skuId: string | null | undefined): string =>
    skuId ? (skuLabelById.get(skuId) ?? skuId.slice(0, 8)) : "";

  // active first, then archived history — both shown, nothing hidden
  const priceRows = [...(prices.data?.data ?? [])].sort((left, right) =>
    left.status === right.status ? 0 : left.status === "active" ? -1 : 1,
  );
  const supplierRows = suppliers.data?.data ?? [];
  const inventoryRows = inventory.data?.data ?? [];
  const totalOnHand = inventoryRows.reduce((sum, item) => sum + item.quantity_on_hand, 0);

  return (
    <div className="drawer-layer" data-testid="product-detail-panel">
      <button className="drawer-scrim" type="button" aria-label={text(zhCN.componentsProductsProductDetailPanel.closeDetails, "Close details")} onClick={onClose} />
      <section ref={panelRef} className="data-drawer product-detail-panel" role="dialog" aria-modal="true" aria-labelledby="product-detail-title">
        <header className="drawer-header">
          <div>
            <h2 id="product-detail-title">{product.name}</h2>
            <p>{product.product_code || text(zhCN.componentsProductsProductDetailPanel.noProductCode, "No product code")} · {text(zhCN.componentsProductsProductDetailPanel.productDetails, "Product details")}</p>
          </div>
          <div className="detail-header-actions">
            {onEdit && <button className="button compact" type="button" onClick={() => onEdit(product)}>{text(zhCN.componentsProductsProductDetailPanel.edit, "Edit")}</button>}
            <button className="button compact quiet" type="button" onClick={onClose}>{text(zhCN.componentsProductsProductDetailPanel.close, "Close")}</button>
          </div>
        </header>
        <div className="product-detail-body">
          <DetailSection title={text(zhCN.componentsProductsProductDetailPanel.basics, "Basics")}>
            <dl className="detail-grid">
              <div className="detail-field"><dt>{text(zhCN.componentsProductsProductDetailPanel.productCode, "Product code")}</dt><dd className="mono-cell">{product.product_code || "—"}</dd></div>
              <div className="detail-field"><dt>{text(zhCN.componentsProductsProductDetailPanel.name, "Name")}</dt><dd>{product.name}</dd></div>
              <div className="detail-field"><dt>{text(zhCN.componentsProductsProductDetailPanel.specification, "Specification")}</dt><dd>{product.spec || "—"}</dd></div>
              <div className="detail-field"><dt>{text(zhCN.componentsProductsProductDetailPanel.unit, "Unit")}</dt><dd>{product.unit || "—"}</dd></div>
              <div className="detail-field"><dt>{text(zhCN.componentsProductsProductDetailPanel.referencePrice, "Reference price")}</dt><dd>{formatMoney(product.list_price, product.currency, language)}</dd></div>
              <div className="detail-field"><dt>{text(zhCN.componentsProductsProductDetailPanel.currency, "Currency")}</dt><dd>{product.currency}</dd></div>
              <div className="detail-field"><dt>{text(zhCN.componentsProductsProductDetailPanel.status, "Status")}</dt><dd><StatusBadge status={product.status} /></dd></div>
              <div className="detail-field"><dt>SKU</dt><dd>{product.has_skus ? text(zhCN.componentsProductsProductDetailPanel.variants(`${product.sku_count}`), `${product.sku_count} variants`) : text(zhCN.componentsProductsProductDetailPanel.noVariants, "No variants")}</dd></div>
              <div className="detail-field"><dt>ID</dt><dd className="mono-cell">{product.id}</dd></div>
              <div className="detail-field"><dt>{text(zhCN.componentsProductsProductDetailPanel.created, "Created")}</dt><dd>{formatTimestamp(product.created_at, language)}</dd></div>
              <div className="detail-field"><dt>{text(zhCN.componentsProductsProductDetailPanel.updated, "Updated")}</dt><dd>{formatTimestamp(product.updated_at, language)}</dd></div>
            </dl>
          </DetailSection>

          <DetailSection title={text(zhCN.componentsProductsProductDetailPanel.additionalFieldsMetadata, "Additional fields (metadata)")}>
            <MetadataBlock metadata={product.metadata} />
          </DetailSection>

          <DetailSection title={text(zhCN.componentsProductsProductDetailPanel.pictures, "Pictures")} count={(images.data?.data ?? []).length}>
            <SectionState
              loading={images.isPending}
              error={images.isError ? apiErrorMessage(images.error) : null}
              empty={Boolean(images.data) && (images.data?.data ?? []).length === 0}
              emptyText={text(zhCN.componentsProductsProductDetailPanel.noPicturesYetUploadAnAttachmentAndLinkIt, "No pictures yet. Upload an attachment and link it to the product, one as primary.")}
            >
              <div className="product-gallery">
                {(images.data?.data ?? []).map((image) => (
                  <figure key={image.id} className={image.is_primary ? "product-gallery-item primary" : "product-gallery-item"}>
                    <img src={productImageContentUrl(product.id, image.attachment_id)} alt={image.caption ?? image.filename ?? ""} loading="lazy" />
                    <figcaption>{image.is_primary ? text(zhCN.componentsProductsProductDetailPanel.primary, "Primary") + " · " : ""}{image.image_type !== "other" ? image.image_type + " · " : ""}{image.caption ?? image.filename ?? ""}</figcaption>
                  </figure>
                ))}
              </div>
            </SectionState>
          </DetailSection>

          <DetailSection title={text(zhCN.componentsProductsProductDetailPanel.priceBook, "Price book")} count={priceRows.length}>
            <SectionState
              loading={prices.isPending}
              error={prices.isError ? apiErrorMessage(prices.error) : null}
              empty={Boolean(prices.data) && priceRows.length === 0}
              emptyText={text(zhCN.componentsProductsProductDetailPanel.noPriceBookEntriesYetTheCatalogReferencePrice, "No price book entries yet. The catalog reference price lives on the product itself.")}
            >
              <div className="table-scroll">
                <table className="data-table">
                  <thead><tr>
                    <th>{text(zhCN.componentsProductsProductDetailPanel.type, "Type")}</th>
                    <th>{text(zhCN.componentsProductsProductDetailPanel.price, "Price")}</th>
                    <th>{text(zhCN.componentsProductsProductDetailPanel.taxIncl, "Tax incl.")}</th>
                    <th>{text(zhCN.componentsProductsProductDetailPanel.tax, "Tax %")}</th>
                    <th>SKU</th>
                    <th>{text(zhCN.componentsProductsProductDetailPanel.status, "Status")}</th>
                    <th>{text(zhCN.componentsProductsProductDetailPanel.time, "Created")}</th>
                    <th>{text(zhCN.componentsProductsProductDetailPanel.meta, "Meta")}</th>
                  </tr></thead>
                  <tbody>
                    {priceRows.map((price) => (
                      <tr key={price.id} className={price.status === "archived" ? "history-row" : undefined}>
                        <td>{priceTypeLabel(price.price_type, text)}</td>
                        <td className="price-cell">{formatMoney(price.price, price.currency, language)}</td>
                        <td>{price.tax_in_price ? text(zhCN.componentsProductsProductDetailPanel.taxIncl, "Yes") : text(zhCN.componentsProductsProductDetailPanel.no, "No")}</td>
                        <td>{price.tax_percentage != null ? `${price.tax_percentage}%` : "—"}</td>
                        <td>{skuLabel(price.sku_id) || text(zhCN.componentsProductsProductDetailPanel.product, "Product")}</td>
                        <td><StatusBadge status={price.status} /></td>
                        <td>{formatTimestamp(price.created_at, language)}</td>
                        <td><MetadataToggle metadata={price.metadata} /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </SectionState>
          </DetailSection>

          <DetailSection title={text(zhCN.componentsProductsProductDetailPanel.suppliers, "Suppliers")} count={supplierRows.length}>
            <SectionState
              loading={suppliers.isPending}
              error={suppliers.isError ? apiErrorMessage(suppliers.error) : null}
              empty={Boolean(suppliers.data) && supplierRows.length === 0}
              emptyText={text(zhCN.componentsProductsProductDetailPanel.noSupplySourcesRecordedYet, "No supply sources recorded yet.")}
            >
              <div className="table-scroll">
                <table className="data-table">
                  <thead><tr>
                    <th>{text(zhCN.componentsProductsProductDetailPanel.rank, "Rank")}</th>
                    <th>{text(zhCN.componentsProductsProductDetailPanel.suppliers, "Vendor")}</th>
                    <th>{text(zhCN.componentsProductsProductDetailPanel.theirCode, "Their code")}</th>
                    <th>{text(zhCN.componentsProductsProductDetailPanel.lastPrice, "Last price")}</th>
                    <th>{text(zhCN.componentsProductsProductDetailPanel.leadDays, "Lead days")}</th>
                    <th>{text(zhCN.componentsProductsProductDetailPanel.mOQ, "MOQ")}</th>
                    <th>{text(zhCN.componentsProductsProductDetailPanel.status, "Status")}</th>
                    <th>{text(zhCN.componentsProductsProductDetailPanel.meta, "Meta")}</th>
                  </tr></thead>
                  <tbody>
                    {supplierRows.map((supplier: SupplierProductRead) => (
                      <tr key={supplier.id} className={supplier.status === "archived" ? "history-row" : undefined}>
                        <td>{supplier.preference ?? "—"}</td>
                        <td>
                          <strong>{supplier.vendor_name || supplier.vendor_id}</strong>
                          {supplier.supplier_product_name && <small className="supplier-alias">{supplier.supplier_product_name}</small>}
                        </td>
                        <td className="mono-cell">{supplier.supplier_product_code || "—"}</td>
                        <td className="price-cell">{formatMoney(supplier.last_price, supplier.currency, language)}</td>
                        <td>{supplier.lead_time_days ?? "—"}</td>
                        <td>{supplier.min_order_quantity ?? "—"}{supplier.order_increment != null && <small className="supplier-alias">{text(zhCN.componentsProductsProductDetailPanel.step, "step")} {supplier.order_increment}</small>}</td>
                        <td><StatusBadge status={supplier.status} /></td>
                        <td><MetadataToggle metadata={supplier.metadata} /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </SectionState>
          </DetailSection>

          <DetailSection title={text(zhCN.componentsProductsProductDetailPanel.inventory, "Inventory")} count={inventoryRows.length}>
            <SectionState
              loading={inventory.isPending}
              error={inventory.isError ? apiErrorMessage(inventory.error) : null}
              empty={Boolean(inventory.data) && inventoryRows.length === 0}
              emptyText={text(zhCN.componentsProductsProductDetailPanel.noInventoryRecordedYet, "No inventory recorded yet.")}
            >
              <p className="inventory-total">{text(zhCN.componentsProductsProductDetailPanel.totalOnHand(`${totalOnHand}`), `Total on hand ${totalOnHand}`)}{product.unit ? ` ${product.unit}` : ""}</p>
              {inventoryRows.map((item) => (
                <InventoryLedger key={item.id} item={item} skuLabel={skuLabel(item.sku_id)} />
              ))}
            </SectionState>
          </DetailSection>
        </div>
      </section>
    </div>
  );
}
