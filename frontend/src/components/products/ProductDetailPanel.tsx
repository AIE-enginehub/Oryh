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
    list: ["目录价", "List"],
    default: ["默认售价", "Default"],
    promo: ["促销价", "Promo"],
    wholesale: ["批发价", "Wholesale"],
    competitive: ["竞品价", "Competitive"],
    minimum: ["最低限价", "Minimum"],
    maximum: ["最高限价", "Maximum"],
    cost: ["成本价", "Cost"],
  };
  const entry = labels[type];
  return entry ? text(entry[0], entry[1]) : type;
}

function movementReasonLabel(reason: InventoryItemDetailRead["reason"], text: LocalText): string {
  const labels: Record<InventoryItemDetailRead["reason"], [string, string]> = {
    initial: ["期初", "Initial"],
    import_initial: ["导入建账", "Import initial"],
    import_override: ["导入覆盖", "Import override"],
    received: ["入库", "Received"],
    issued: ["出库", "Issued"],
    adjustment: ["盘点调整", "Adjustment"],
    damaged: ["损坏", "Damaged"],
    returned: ["退回", "Returned"],
    transfer: ["调拨", "Transfer"],
    reserved: ["占货", "Reserved"],
    reservation_released: ["释放占货", "Hold released"],
    other: ["其他", "Other"],
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
    return <p className="muted-value">{text("无附加字段。", "No additional fields.")}</p>;
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
      <summary>{text("查看", "View")}</summary>
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
  if (loading) return <p className="muted-value">{text("加载中…", "Loading…")}</p>;
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
          {item.facility || text("未指定仓库", "No facility")}
          {item.lot_id && <small>{text("批号", "Lot")} {item.lot_id}</small>}
          {item.bin_number && <small>{text("库位", "Bin")} {item.bin_number}</small>}
          {skuLabel && <small>SKU {skuLabel}</small>}
        </span>
        <span className="inventory-numbers">
          <b>{item.quantity_on_hand}</b>
          <small>{text("可用", "ATP")} {item.available_to_promise}</small>
          {item.expire_date && <small>{text("效期", "Expires")} {item.expire_date}</small>}
          {item.unit_cost != null && <small>{text("成本", "Cost")} {formatMoney(item.unit_cost, item.currency, language)}</small>}
          <StatusBadge status={item.status} />
        </span>
      </summary>
      <SectionState
        loading={open && ledger.isPending}
        error={ledger.isError ? apiErrorMessage(ledger.error) : null}
        empty={Boolean(ledger.data) && rows.length === 0}
        emptyText={text("该库存还没有变动记录。", "No movements recorded for this item.")}
      >
        <div className="table-scroll">
          <table className="data-table ledger-table">
            <thead><tr>
              <th>{text("时间", "Time")}</th>
              <th>{text("原因", "Reason")}</th>
              <th>{text("数量变动", "Qty change")}</th>
              <th>{text("可用变动", "ATP change")}</th>
              <th>{text("说明", "Description")}</th>
              <th>{text("操作者", "By")}</th>
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
      <button className="drawer-scrim" type="button" aria-label={text("关闭详情", "Close details")} onClick={onClose} />
      <section ref={panelRef} className="data-drawer product-detail-panel" role="dialog" aria-modal="true" aria-labelledby="product-detail-title">
        <header className="drawer-header">
          <div>
            <h2 id="product-detail-title">{product.name}</h2>
            <p>{product.product_code || text("未设置产品编号", "No product code")} · {text("产品详情", "Product details")}</p>
          </div>
          <div className="detail-header-actions">
            {onEdit && <button className="button compact" type="button" onClick={() => onEdit(product)}>{text("编辑", "Edit")}</button>}
            <button className="button compact quiet" type="button" onClick={onClose}>{text("关闭", "Close")}</button>
          </div>
        </header>
        <div className="product-detail-body">
          <DetailSection title={text("基本信息", "Basics")}>
            <dl className="detail-grid">
              <div className="detail-field"><dt>{text("产品编号", "Product code")}</dt><dd className="mono-cell">{product.product_code || "—"}</dd></div>
              <div className="detail-field"><dt>{text("名称", "Name")}</dt><dd>{product.name}</dd></div>
              <div className="detail-field"><dt>{text("规格", "Specification")}</dt><dd>{product.spec || "—"}</dd></div>
              <div className="detail-field"><dt>{text("单位", "Unit")}</dt><dd>{product.unit || "—"}</dd></div>
              <div className="detail-field"><dt>{text("参考价格", "Reference price")}</dt><dd>{formatMoney(product.list_price, product.currency, language)}</dd></div>
              <div className="detail-field"><dt>{text("币种", "Currency")}</dt><dd>{product.currency}</dd></div>
              <div className="detail-field"><dt>{text("状态", "Status")}</dt><dd><StatusBadge status={product.status} /></dd></div>
              <div className="detail-field"><dt>SKU</dt><dd>{product.has_skus ? text(`${product.sku_count} 个变体`, `${product.sku_count} variants`) : text("无变体", "No variants")}</dd></div>
              <div className="detail-field"><dt>ID</dt><dd className="mono-cell">{product.id}</dd></div>
              <div className="detail-field"><dt>{text("创建时间", "Created")}</dt><dd>{formatTimestamp(product.created_at, language)}</dd></div>
              <div className="detail-field"><dt>{text("更新时间", "Updated")}</dt><dd>{formatTimestamp(product.updated_at, language)}</dd></div>
            </dl>
          </DetailSection>

          <DetailSection title={text("附加字段 (metadata)", "Additional fields (metadata)")}>
            <MetadataBlock metadata={product.metadata} />
          </DetailSection>

          <DetailSection title={text("图片", "Pictures")} count={(images.data?.data ?? []).length}>
            <SectionState
              loading={images.isPending}
              error={images.isError ? apiErrorMessage(images.error) : null}
              empty={Boolean(images.data) && (images.data?.data ?? []).length === 0}
              emptyText={text("还没有图片。上传附件后挂到产品上，一张主图。", "No pictures yet. Upload an attachment and link it to the product, one as primary.")}
            >
              <div className="product-gallery">
                {(images.data?.data ?? []).map((image) => (
                  <figure key={image.id} className={image.is_primary ? "product-gallery-item primary" : "product-gallery-item"}>
                    <img src={productImageContentUrl(product.id, image.attachment_id)} alt={image.caption ?? image.filename ?? ""} loading="lazy" />
                    <figcaption>{image.is_primary ? text("主图", "Primary") + " · " : ""}{image.image_type !== "other" ? image.image_type + " · " : ""}{image.caption ?? image.filename ?? ""}</figcaption>
                  </figure>
                ))}
              </div>
            </SectionState>
          </DetailSection>

          <DetailSection title={text("价格簿", "Price book")} count={priceRows.length}>
            <SectionState
              loading={prices.isPending}
              error={prices.isError ? apiErrorMessage(prices.error) : null}
              empty={Boolean(prices.data) && priceRows.length === 0}
              emptyText={text("还没有价格簿条目。目录参考价维护在产品字段上。", "No price book entries yet. The catalog reference price lives on the product itself.")}
            >
              <div className="table-scroll">
                <table className="data-table">
                  <thead><tr>
                    <th>{text("类型", "Type")}</th>
                    <th>{text("价格", "Price")}</th>
                    <th>{text("含税", "Tax incl.")}</th>
                    <th>{text("税率", "Tax %")}</th>
                    <th>SKU</th>
                    <th>{text("状态", "Status")}</th>
                    <th>{text("时间", "Created")}</th>
                    <th>{text("附加", "Meta")}</th>
                  </tr></thead>
                  <tbody>
                    {priceRows.map((price) => (
                      <tr key={price.id} className={price.status === "archived" ? "history-row" : undefined}>
                        <td>{priceTypeLabel(price.price_type, text)}</td>
                        <td className="price-cell">{formatMoney(price.price, price.currency, language)}</td>
                        <td>{price.tax_in_price ? text("含税", "Yes") : text("不含税", "No")}</td>
                        <td>{price.tax_percentage != null ? `${price.tax_percentage}%` : "—"}</td>
                        <td>{skuLabel(price.sku_id) || text("产品级", "Product")}</td>
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

          <DetailSection title={text("供应商", "Suppliers")} count={supplierRows.length}>
            <SectionState
              loading={suppliers.isPending}
              error={suppliers.isError ? apiErrorMessage(suppliers.error) : null}
              empty={Boolean(suppliers.data) && supplierRows.length === 0}
              emptyText={text("还没有供应商供货记录。", "No supply sources recorded yet.")}
            >
              <div className="table-scroll">
                <table className="data-table">
                  <thead><tr>
                    <th>{text("优先", "Rank")}</th>
                    <th>{text("供应商", "Vendor")}</th>
                    <th>{text("供应商货号", "Their code")}</th>
                    <th>{text("最近价格", "Last price")}</th>
                    <th>{text("交期(天)", "Lead days")}</th>
                    <th>{text("起订量", "MOQ")}</th>
                    <th>{text("状态", "Status")}</th>
                    <th>{text("附加", "Meta")}</th>
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
                        <td>{supplier.min_order_quantity ?? "—"}{supplier.order_increment != null && <small className="supplier-alias">{text("增量", "step")} {supplier.order_increment}</small>}</td>
                        <td><StatusBadge status={supplier.status} /></td>
                        <td><MetadataToggle metadata={supplier.metadata} /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </SectionState>
          </DetailSection>

          <DetailSection title={text("库存", "Inventory")} count={inventoryRows.length}>
            <SectionState
              loading={inventory.isPending}
              error={inventory.isError ? apiErrorMessage(inventory.error) : null}
              empty={Boolean(inventory.data) && inventoryRows.length === 0}
              emptyText={text("还没有库存记录。", "No inventory recorded yet.")}
            >
              <p className="inventory-total">{text(`在库合计 ${totalOnHand}`, `Total on hand ${totalOnHand}`)}{product.unit ? ` ${product.unit}` : ""}</p>
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
