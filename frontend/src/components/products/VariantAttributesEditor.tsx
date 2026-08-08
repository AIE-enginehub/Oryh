import { useI18n } from "../../i18n";

export type AttributeRow = {
  id: number;
  key: string;
  value: string;
  valueType: "string" | "json";
};

let nextRowId = 1;

export function emptyAttributeRow(): AttributeRow {
  return { id: nextRowId++, key: "", value: "", valueType: "string" };
}

export function attributesToRows(attributes: Record<string, unknown>): AttributeRow[] {
  const rows = Object.entries(attributes).map(([key, value]) => {
    const isString = typeof value === "string";
    return {
      id: nextRowId++,
      key,
      value: isString ? value : (JSON.stringify(value) ?? ""),
      valueType: isString ? "string" as const : "json" as const,
    };
  });
  return rows.length > 0 ? rows : [emptyAttributeRow()];
}

type VariantAttributesEditorProps = {
  rows: AttributeRow[];
  onChange: (rows: AttributeRow[]) => void;
};

export function VariantAttributesEditor({ rows, onChange }: VariantAttributesEditorProps) {
  const { text } = useI18n();
  const update = (id: number, field: "key" | "value", value: string) => {
    onChange(rows.map((row) => row.id === id ? { ...row, [field]: value } : row));
  };

  const remove = (id: number) => {
    const remaining = rows.filter((row) => row.id !== id);
    onChange(remaining.length > 0 ? remaining : [emptyAttributeRow()]);
  };

  return (
    <fieldset className="variant-editor">
      <legend>{text("规格属性", "Variant attributes")}</legend>
      <p>{text("用名称和值描述 SKU，例如“颜色 / 深空灰”“尺码 / L”。", "Describe the SKU with names and values, for example “Color / Space Gray” or “Size / L”.")}</p>
      <div className="variant-rows">
        {rows.map((row, index) => (
          <div className="variant-row" key={row.id}>
            <label>
              <span className="sr-only">{text(`属性 ${index + 1} 名称`, `Attribute ${index + 1} name`)}</span>
              <input
                aria-label={text(`属性 ${index + 1} 名称`, `Attribute ${index + 1} name`)}
                maxLength={100}
                placeholder={text("属性名称", "Attribute name")}
                value={row.key}
                onChange={(event) => update(row.id, "key", event.target.value)}
              />
            </label>
            <span className="variant-divider" aria-hidden="true">/</span>
            <label>
              <span className="sr-only">{text(`属性 ${index + 1} 值`, `Attribute ${index + 1} value`)}</span>
              <input
                aria-label={text(`属性 ${index + 1} 值`, `Attribute ${index + 1} value`)}
                maxLength={200}
                placeholder={text("属性值", "Attribute value")}
                value={row.value}
                onChange={(event) => update(row.id, "value", event.target.value)}
              />
              {row.valueType === "json" && <small>{text("结构化内容", "Structured content")}</small>}
            </label>
            <button className="variant-remove" type="button" aria-label={text(`删除第 ${index + 1} 行属性`, `Remove attribute row ${index + 1}`)} onClick={() => remove(row.id)}>×</button>
          </div>
        ))}
      </div>
      <button className="button compact" type="button" onClick={() => onChange([...rows, emptyAttributeRow()])}>{text("＋ 添加属性", "+ Add attribute")}</button>
    </fieldset>
  );
}
