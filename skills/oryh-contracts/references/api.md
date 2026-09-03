# Oryh Contracts API Reference

{{include:_common/api-auth-principal.md}}

Reads and writes both require `contract.manage`, scoped by side:
`contract.manage:purchase` reaches contracts whose counterparty is a
vendor, `:sales` those with a customer; the unscoped grant reaches both.

```text
GET    /contracts?side=&contract_type=&vendor_id=&customer_id=&parent_contract_id=&status=&keyword=
POST   /contracts                     → {title, contract_type, vendor_id | customer_id, total_amount?, dates…, items?: [...]}
GET    /contracts/{contract_id}       → header + items + documents (no text) + terms_by_type
PATCH  /contracts/{contract_id}       → status (signed stamps signed_at); agreement fields only while draft/negotiating; summary/remarks always
DELETE /contracts/{contract_id} · POST /contracts/{contract_id}/restore
GET    /contracts/{contract_id}/execution     → orders/invoices/payments under it, contracted vs ordered by product (derived)
GET    /contracts/{contract_id}/attachments/{attachment_id}/content   → an original's bytes

GET    /contract-items?contract_id=   · POST /contract-items · PATCH /contract-items/{item_id} · DELETE   (editable states only)

POST   /attachments                   → {filename, content_type (any), content_base64}; 10 MB per file
GET    /contract-documents?contract_id=&document_type=&keyword=   → keyword searches extracted_text and returns it
POST   /contract-documents            → {contract_id, attachment_id, document_type, page_no?, sort_order?, caption?, extracted_text?}
GET    /contract-documents/{document_id}      → with extracted_text
PATCH  /contract-documents/{document_id}      → extracted_text, type, order, caption
DELETE /contract-documents/{document_id}      → removes the link; terms pointing at it keep their words, lose the page

GET    /contract-terms?contract_id=&term_type=&keyword=          → THE clause lookup
POST   /contract-terms                → {contract_id, term_type, content (verbatim), clause_ref?, title?, summary?, document_id?, page_no?}
PATCH  /contract-terms/{term_id} · DELETE /contract-terms/{term_id}

GET    /type-options?family=contract_type | contract_term_type | contract_document_type
```

```json
POST /contract-terms
{
  "contract_id": "contract-id",
  "term_type": "payment_terms",
  "clause_ref": "5",
  "content": "Article 5 Payment: 30% of the contract price within three working days of signing, as deposit; 60% before the first shipment; the remaining 10% after acceptance.",
  "summary": "30% deposit within 3 working days of signing; 60% before the first shipment; 10% after acceptance",
  "document_id": "document-id",
  "page_no": 7
}
```
