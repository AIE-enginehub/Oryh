--
-- ORYH database schema — GENERATED FILE, DO NOT EDIT.
--
-- Regenerate with: scripts/dump_schema_snapshot.sh
--
-- Source of truth is alembic/versions/; this is a readable snapshot of where
-- those migrations land, dumped from a database migrated to head. The "why"
-- behind any table lives in its migration's docstring, not here.
--
-- Alembic revision: 20260804_0046
--

--
-- PostgreSQL database dump
--



SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: oryh; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA oryh;


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: alembic_version; Type: TABLE; Schema: oryh; Owner: -
--

CREATE TABLE oryh.alembic_version (
    version_num character varying(32) NOT NULL
);


--
-- Name: api_keys; Type: TABLE; Schema: oryh; Owner: -
--

CREATE TABLE oryh.api_keys (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id uuid NOT NULL,
    key_hash text NOT NULL,
    label text,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    user_id uuid,
    role text DEFAULT 'service'::text NOT NULL,
    principal_kind character varying(30) DEFAULT 'tenant_service'::character varying NOT NULL
);


--
-- Name: approval_records; Type: TABLE; Schema: oryh; Owner: -
--

CREATE TABLE oryh.approval_records (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id uuid NOT NULL,
    entity_type text NOT NULL,
    entity_id uuid NOT NULL,
    round_no integer DEFAULT 1 NOT NULL,
    sequence_no integer DEFAULT 1 NOT NULL,
    action text NOT NULL,
    approver_id text,
    approver_role text,
    comment text,
    source text,
    metadata_jsonb jsonb DEFAULT '{}'::jsonb NOT NULL,
    acted_at timestamp with time zone NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT approval_records_action_chk CHECK ((action = ANY (ARRAY['submitted'::text, 'approved'::text, 'rejected'::text, 'returned'::text, 'commented'::text]))),
    CONSTRAINT approval_records_entity_type_chk CHECK ((entity_type = ANY (ARRAY['timesheet_header'::text, 'expense_claim'::text, 'purchase_request'::text, 'sales_quotation'::text, 'sales_order'::text, 'approval_target'::text, 'business_object'::text]))),
    CONSTRAINT approval_records_round_no_chk CHECK ((round_no >= 1)),
    CONSTRAINT approval_records_sequence_no_chk CHECK ((sequence_no >= 1)),
    CONSTRAINT approval_records_source_chk CHECK (((source = ANY (ARRAY['web'::text, 'api'::text, 'ai'::text, 'system'::text])) OR (source IS NULL)))
);


--
-- Name: attachments; Type: TABLE; Schema: oryh; Owner: -
--

CREATE TABLE oryh.attachments (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id uuid NOT NULL,
    filename text NOT NULL,
    content_type text NOT NULL,
    size_bytes integer NOT NULL,
    sha256 text NOT NULL,
    content bytea NOT NULL,
    uploaded_by text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT attachments_size_chk CHECK ((size_bytes >= 0))
);


--
-- Name: audit_logs; Type: TABLE; Schema: oryh; Owner: -
--

CREATE TABLE oryh.audit_logs (
    id bigint NOT NULL,
    tenant_id uuid NOT NULL,
    action text NOT NULL,
    entity_type text NOT NULL,
    entity_id uuid NOT NULL,
    actor text,
    detail_jsonb jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: audit_logs_id_seq; Type: SEQUENCE; Schema: oryh; Owner: -
--

CREATE SEQUENCE oryh.audit_logs_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: audit_logs_id_seq; Type: SEQUENCE OWNED BY; Schema: oryh; Owner: -
--

ALTER SEQUENCE oryh.audit_logs_id_seq OWNED BY oryh.audit_logs.id;


--
-- Name: billing_account_entries; Type: TABLE; Schema: oryh; Owner: -
--

CREATE TABLE oryh.billing_account_entries (
    id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    billing_account_id uuid NOT NULL,
    amount numeric(14,2) NOT NULL,
    reason character varying(30) NOT NULL,
    description character varying(500),
    entity_type character varying(50),
    entity_id uuid,
    expires_at timestamp with time zone,
    effective_at timestamp with time zone DEFAULT now() NOT NULL,
    idempotency_key character varying(64),
    created_by character varying(100),
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    idempotency_seq integer
);


--
-- Name: billing_accounts; Type: TABLE; Schema: oryh; Owner: -
--

CREATE TABLE oryh.billing_accounts (
    id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    account_code character varying(64) NOT NULL,
    name character varying(200) NOT NULL,
    unit_type character varying(10) NOT NULL,
    unit character varying(30) NOT NULL,
    customer_id uuid,
    vendor_id uuid,
    employee_id uuid,
    owner_name_snapshot character varying(200),
    credit_limit numeric(14,2) DEFAULT 0 NOT NULL,
    balance numeric(14,2) DEFAULT 0 NOT NULL,
    valid_from date,
    valid_until date,
    status text DEFAULT 'active'::text NOT NULL,
    external_account_id character varying(64),
    description text,
    remarks text,
    source_report_text text,
    custom_fields_jsonb jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    deleted_at timestamp with time zone,
    CONSTRAINT billing_accounts_credit_limit_ck CHECK ((credit_limit >= (0)::numeric)),
    CONSTRAINT billing_accounts_single_owner_ck CHECK ((((
CASE
    WHEN (customer_id IS NULL) THEN 0
    ELSE 1
END +
CASE
    WHEN (vendor_id IS NULL) THEN 0
    ELSE 1
END) +
CASE
    WHEN (employee_id IS NULL) THEN 0
    ELSE 1
END) = 1)),
    CONSTRAINT billing_accounts_unit_type_ck CHECK (((unit_type)::text = ANY ((ARRAY['currency'::character varying, 'points'::character varying])::text[])))
);


--
-- Name: business_object_links; Type: TABLE; Schema: oryh; Owner: -
--

CREATE TABLE oryh.business_object_links (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id uuid NOT NULL,
    source_object_id uuid NOT NULL,
    target_object_id uuid NOT NULL,
    link_type text NOT NULL,
    metadata_jsonb jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT business_object_links_distinct_objects_chk CHECK ((source_object_id <> target_object_id))
);


--
-- Name: business_objects; Type: TABLE; Schema: oryh; Owner: -
--

CREATE TABLE oryh.business_objects (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id uuid NOT NULL,
    object_type text NOT NULL,
    title text NOT NULL,
    summary text,
    payload_jsonb jsonb DEFAULT '{}'::jsonb NOT NULL,
    source_text text,
    status text DEFAULT 'open'::text NOT NULL,
    created_by text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    deleted_at timestamp with time zone,
    deleted_by text,
    delete_reason text
);


--
-- Name: capabilities; Type: TABLE; Schema: oryh; Owner: -
--

CREATE TABLE oryh.capabilities (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id uuid NOT NULL,
    name text NOT NULL,
    kind text DEFAULT 'custom'::text NOT NULL,
    title text,
    description text,
    scopable boolean DEFAULT false NOT NULL,
    created_by text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT capabilities_kind_chk CHECK ((kind = ANY (ARRAY['system'::text, 'custom'::text])))
);


--
-- Name: customers; Type: TABLE; Schema: oryh; Owner: -
--

CREATE TABLE oryh.customers (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id uuid NOT NULL,
    customer_code text,
    name text NOT NULL,
    tax_id text,
    contact text,
    email text,
    phone text,
    address text,
    status text DEFAULT 'active'::text NOT NULL,
    metadata_jsonb jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    customer_kind text,
    customer_type text,
    CONSTRAINT customers_kind_ck CHECK (((customer_kind IS NULL) OR (customer_kind = ANY (ARRAY['person'::text, 'company'::text])))),
    CONSTRAINT customers_status_chk CHECK ((status = ANY (ARRAY['active'::text, 'archived'::text])))
);


--
-- Name: device_authorizations; Type: TABLE; Schema: oryh; Owner: -
--

CREATE TABLE oryh.device_authorizations (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    device_code_hash text NOT NULL,
    user_code text NOT NULL,
    client_name text,
    status text DEFAULT 'pending'::text NOT NULL,
    tenant_id uuid,
    user_id uuid,
    api_key_id uuid,
    api_key_plaintext text,
    expires_at timestamp with time zone NOT NULL,
    approved_at timestamp with time zone,
    consumed_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT device_authorizations_status_chk CHECK ((status = ANY (ARRAY['pending'::text, 'approved'::text, 'denied'::text, 'consumed'::text])))
);


--
-- Name: employees; Type: TABLE; Schema: oryh; Owner: -
--

CREATE TABLE oryh.employees (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id uuid NOT NULL,
    employee_code text,
    name text NOT NULL,
    email text,
    timezone text,
    status text DEFAULT 'active'::text NOT NULL,
    metadata_jsonb jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT employees_status_chk CHECK ((status = ANY (ARRAY['active'::text, 'inactive'::text])))
);


--
-- Name: enterprise_pilot_applications; Type: TABLE; Schema: oryh; Owner: -
--

CREATE TABLE oryh.enterprise_pilot_applications (
    id uuid NOT NULL,
    company_name character varying(200) NOT NULL,
    email character varying(320) NOT NULL,
    email_domain character varying(255) NOT NULL,
    company_size character varying(20) NOT NULL,
    agents_jsonb jsonb DEFAULT '[]'::jsonb NOT NULL,
    other_agents character varying(500),
    agent_management character varying(30) NOT NULL,
    weekly_active_agent_users integer,
    workflows_jsonb jsonb DEFAULT '[]'::jsonb NOT NULL,
    other_workflow character varying(500),
    agent_write_readiness character varying(50) NOT NULL,
    executive_sponsor_role character varying(200),
    pilot_timing character varying(30) NOT NULL,
    notes character varying(2000),
    privacy_policy_version character varying(20) NOT NULL,
    privacy_accepted_at timestamp with time zone NOT NULL,
    acknowledgement_sent_at timestamp with time zone,
    status character varying(20) DEFAULT 'submitted'::character varying NOT NULL,
    reviewed_at timestamp with time zone,
    reviewed_by uuid,
    review_note character varying(1000),
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT enterprise_pilot_applications_status_chk CHECK (((status)::text = ANY ((ARRAY['submitted'::character varying, 'contacted'::character varying, 'accepted'::character varying, 'rejected'::character varying])::text[]))),
    CONSTRAINT enterprise_pilot_applications_weekly_users_chk CHECK (((weekly_active_agent_users IS NULL) OR ((weekly_active_agent_users >= 0) AND (weekly_active_agent_users <= 1000000))))
);


--
-- Name: expense_claims; Type: TABLE; Schema: oryh; Owner: -
--

CREATE TABLE oryh.expense_claims (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id uuid NOT NULL,
    employee_id uuid NOT NULL,
    title text NOT NULL,
    claim_date date,
    currency text DEFAULT 'CNY'::text NOT NULL,
    status text DEFAULT 'draft'::text NOT NULL,
    submitted_at timestamp with time zone,
    source_report_text text,
    custom_fields_jsonb jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    deleted_at timestamp with time zone,
    deleted_by text,
    delete_reason text,
    applied_amount numeric(12,2) DEFAULT 0 NOT NULL
);


--
-- Name: expense_items; Type: TABLE; Schema: oryh; Owner: -
--

CREATE TABLE oryh.expense_items (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id uuid NOT NULL,
    claim_id uuid NOT NULL,
    employee_id uuid NOT NULL,
    expense_date date NOT NULL,
    category text DEFAULT 'other'::text NOT NULL,
    amount numeric(12,2) NOT NULL,
    tax_amount numeric(12,2),
    vendor_id uuid,
    merchant text,
    invoice_number text,
    invoice_type text,
    project_id uuid,
    project_name_snapshot text,
    client text,
    attachment_id uuid,
    extracted_fields_jsonb jsonb DEFAULT '{}'::jsonb NOT NULL,
    notes text,
    custom_fields_jsonb jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    deleted_at timestamp with time zone,
    CONSTRAINT expense_items_amount_chk CHECK ((amount > (0)::numeric)),
    CONSTRAINT expense_items_tax_amount_chk CHECK (((tax_amount IS NULL) OR (tax_amount >= (0)::numeric)))
);


--
-- Name: flow_runs; Type: TABLE; Schema: oryh; Owner: -
--

CREATE TABLE oryh.flow_runs (
    id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    subscription_id uuid,
    entity_type character varying(100) NOT NULL,
    trigger character varying(20) DEFAULT 'cadence'::character varying NOT NULL,
    status character varying(20) DEFAULT 'running'::character varying NOT NULL,
    started_at timestamp with time zone NOT NULL,
    finished_at timestamp with time zone,
    queue_size integer,
    items_advanced integer,
    error text,
    detail_jsonb jsonb DEFAULT '{}'::jsonb NOT NULL,
    recorded_by character varying(100),
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone
);


--
-- Name: flow_subscriptions; Type: TABLE; Schema: oryh; Owner: -
--

CREATE TABLE oryh.flow_subscriptions (
    id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    entity_type character varying(100) NOT NULL,
    driver_skill character varying(150) NOT NULL,
    queue_filter_jsonb jsonb DEFAULT '{}'::jsonb NOT NULL,
    cadence_seconds integer DEFAULT 300 NOT NULL,
    enabled boolean DEFAULT true NOT NULL,
    api_key_id uuid,
    created_by character varying(100),
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone,
    unmoved_runs integer DEFAULT 0 NOT NULL,
    parked_at timestamp with time zone,
    parked_reason text
);


--
-- Name: inventory_item_details; Type: TABLE; Schema: oryh; Owner: -
--

CREATE TABLE oryh.inventory_item_details (
    id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    inventory_item_id uuid NOT NULL,
    quantity_on_hand_diff numeric(12,2) NOT NULL,
    available_to_promise_diff numeric(12,2) NOT NULL,
    reason character varying(30) NOT NULL,
    description character varying(500),
    entity_type character varying(50),
    entity_id uuid,
    unit_cost numeric(12,2),
    effective_at timestamp with time zone DEFAULT now() NOT NULL,
    created_by character varying(100),
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: inventory_items; Type: TABLE; Schema: oryh; Owner: -
--

CREATE TABLE oryh.inventory_items (
    id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    product_id uuid NOT NULL,
    sku_id uuid,
    facility character varying(100) DEFAULT ''::character varying NOT NULL,
    lot_id character varying(64) DEFAULT ''::character varying NOT NULL,
    bin_number character varying(64),
    expire_date date,
    received_at timestamp with time zone,
    quantity_on_hand numeric(12,2) DEFAULT 0 NOT NULL,
    available_to_promise numeric(12,2) DEFAULT 0 NOT NULL,
    unit_cost numeric(12,2),
    currency character varying(3) DEFAULT 'CNY'::character varying NOT NULL,
    status text DEFAULT 'active'::text NOT NULL,
    metadata_jsonb jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: invoice_items; Type: TABLE; Schema: oryh; Owner: -
--

CREATE TABLE oryh.invoice_items (
    id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    invoice_id uuid NOT NULL,
    line_no integer,
    invoice_item_type character varying(30) DEFAULT 'goods'::character varying NOT NULL,
    product_id uuid,
    sku_id uuid,
    product_name_snapshot character varying(200),
    spec character varying(200),
    quantity numeric(12,2),
    unit character varying(50),
    unit_price numeric(12,2),
    amount numeric(12,2),
    tax_rate numeric(5,2),
    tax_amount numeric(12,2),
    sales_order_item_id uuid,
    purchase_order_item_id uuid,
    notes text,
    custom_fields_jsonb jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    deleted_at timestamp with time zone,
    pay_history_id uuid
);


--
-- Name: invoices; Type: TABLE; Schema: oryh; Owner: -
--

CREATE TABLE oryh.invoices (
    id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    invoice_no character varying(64) NOT NULL,
    direction character varying(10) NOT NULL,
    invoice_type character varying(30),
    employee_id uuid NOT NULL,
    customer_id uuid,
    vendor_id uuid,
    counterparty_name_snapshot character varying(200),
    title character varying(200) NOT NULL,
    invoice_date date,
    due_date date,
    currency character varying(3) DEFAULT 'CNY'::character varying NOT NULL,
    total_amount numeric(12,2),
    tax_amount numeric(12,2),
    applied_amount numeric(12,2) DEFAULT 0 NOT NULL,
    tax_invoice_code character varying(32),
    tax_invoice_number character varying(64),
    extracted_fields_jsonb jsonb DEFAULT '{}'::jsonb NOT NULL,
    attachment_id uuid,
    sales_order_id uuid,
    purchase_order_id uuid,
    project_id uuid,
    status text DEFAULT 'draft'::text NOT NULL,
    submitted_at timestamp with time zone,
    issued_at timestamp with time zone,
    remarks text,
    source_report_text text,
    custom_fields_jsonb jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    deleted_at timestamp with time zone,
    deleted_by character varying(100),
    delete_reason text,
    billing_account_id uuid,
    payee_employee_id uuid,
    period_start date,
    period_end date,
    CONSTRAINT invoices_direction_counterparty_ck CHECK (((((direction)::text = 'sales'::text) AND (customer_id IS NOT NULL) AND (vendor_id IS NULL) AND (payee_employee_id IS NULL)) OR (((direction)::text = 'purchase'::text) AND (vendor_id IS NOT NULL) AND (customer_id IS NULL) AND (payee_employee_id IS NULL)) OR (((direction)::text = 'payroll'::text) AND (payee_employee_id IS NOT NULL) AND (customer_id IS NULL) AND (vendor_id IS NULL))))
);


--
-- Name: object_type_definitions; Type: TABLE; Schema: oryh; Owner: -
--

CREATE TABLE oryh.object_type_definitions (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id uuid NOT NULL,
    object_type text NOT NULL,
    title text,
    description text,
    json_schema jsonb DEFAULT '{}'::jsonb NOT NULL,
    version integer DEFAULT 1 NOT NULL,
    status text DEFAULT 'active'::text NOT NULL,
    created_by text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    entity_kind text DEFAULT 'business_object'::text NOT NULL,
    state_machine jsonb,
    CONSTRAINT object_type_definitions_entity_kind_chk CHECK ((entity_kind = ANY (ARRAY['business_object'::text, 'builtin'::text]))),
    CONSTRAINT object_type_definitions_status_chk CHECK ((status = ANY (ARRAY['active'::text, 'archived'::text]))),
    CONSTRAINT object_type_definitions_version_chk CHECK ((version >= 1))
);


--
-- Name: pay_histories; Type: TABLE; Schema: oryh; Owner: -
--

CREATE TABLE oryh.pay_histories (
    id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    employee_id uuid NOT NULL,
    effective_from date NOT NULL,
    effective_thru date,
    amount numeric(14,2),
    period_type character varying(20) DEFAULT 'month'::character varying NOT NULL,
    currency character varying(3) DEFAULT 'CNY'::character varying NOT NULL,
    notes text,
    created_by character varying(100),
    custom_fields_jsonb jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    component character varying(30) DEFAULT 'base_salary'::character varying NOT NULL,
    rate numeric(9,6),
    basis character varying(200),
    formula text,
    CONSTRAINT pay_histories_amount_ck CHECK (((amount IS NULL) OR (amount >= (0)::numeric))),
    CONSTRAINT pay_histories_period_ck CHECK (((effective_thru IS NULL) OR (effective_thru >= effective_from))),
    CONSTRAINT pay_histories_rate_basis_ck CHECK (((rate IS NULL) OR (basis IS NOT NULL))),
    CONSTRAINT pay_histories_rate_ck CHECK (((rate IS NULL) OR (rate >= (0)::numeric))),
    CONSTRAINT pay_histories_states_something_ck CHECK (((amount IS NOT NULL) OR (rate IS NOT NULL) OR (formula IS NOT NULL)))
);


--
-- Name: payment_applications; Type: TABLE; Schema: oryh; Owner: -
--

CREATE TABLE oryh.payment_applications (
    id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    payment_id uuid NOT NULL,
    invoice_id uuid,
    invoice_item_id uuid,
    expense_claim_id uuid,
    to_payment_id uuid,
    amount_applied numeric(12,2) NOT NULL,
    note character varying(500),
    idempotency_key character varying(64),
    applied_at timestamp with time zone DEFAULT now() NOT NULL,
    created_by character varying(100),
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    billing_account_id uuid,
    idempotency_seq integer,
    CONSTRAINT payment_applications_item_needs_invoice_ck CHECK (((invoice_item_id IS NULL) OR (invoice_id IS NOT NULL))),
    CONSTRAINT payment_applications_single_target_ck CHECK (((((
CASE
    WHEN (invoice_id IS NULL) THEN 0
    ELSE 1
END +
CASE
    WHEN (expense_claim_id IS NULL) THEN 0
    ELSE 1
END) +
CASE
    WHEN (billing_account_id IS NULL) THEN 0
    ELSE 1
END) +
CASE
    WHEN (to_payment_id IS NULL) THEN 0
    ELSE 1
END) = 1))
);


--
-- Name: payments; Type: TABLE; Schema: oryh; Owner: -
--

CREATE TABLE oryh.payments (
    id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    payment_no character varying(64) NOT NULL,
    direction character varying(10) NOT NULL,
    payment_method character varying(30),
    employee_id uuid NOT NULL,
    customer_id uuid,
    vendor_id uuid,
    payee_employee_id uuid,
    counterparty_name_snapshot character varying(200),
    payment_date date,
    amount numeric(12,2) NOT NULL,
    currency character varying(3) DEFAULT 'CNY'::character varying NOT NULL,
    applied_amount numeric(12,2) DEFAULT 0 NOT NULL,
    bank_account character varying(200),
    counterparty_account character varying(200),
    reference_no character varying(100),
    attachment_id uuid,
    status text DEFAULT 'draft'::text NOT NULL,
    submitted_at timestamp with time zone,
    paid_at timestamp with time zone,
    remarks text,
    source_report_text text,
    custom_fields_jsonb jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    deleted_at timestamp with time zone,
    CONSTRAINT payments_amount_positive_ck CHECK ((amount > (0)::numeric)),
    CONSTRAINT payments_single_counterparty_ck CHECK ((((
CASE
    WHEN (customer_id IS NULL) THEN 0
    ELSE 1
END +
CASE
    WHEN (vendor_id IS NULL) THEN 0
    ELSE 1
END) +
CASE
    WHEN (payee_employee_id IS NULL) THEN 0
    ELSE 1
END) = 1))
);


--
-- Name: pending_registrations; Type: TABLE; Schema: oryh; Owner: -
--

CREATE TABLE oryh.pending_registrations (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    company_name text NOT NULL,
    email text NOT NULL,
    email_domain text NOT NULL,
    password_hash text,
    token_hash text,
    expires_at timestamp with time zone NOT NULL,
    consumed_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    status character varying(20) DEFAULT 'pending_email'::character varying NOT NULL,
    verification_sent_at timestamp with time zone DEFAULT now() NOT NULL,
    verified_at timestamp with time zone,
    reviewed_at timestamp with time zone,
    reviewed_by uuid,
    rejection_reason character varying(500),
    tenant_id uuid,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT pending_registrations_status_chk CHECK (((status)::text = ANY ((ARRAY['pending_email'::character varying, 'pending_review'::character varying, 'approved'::character varying, 'rejected'::character varying])::text[])))
);


--
-- Name: platform_admins; Type: TABLE; Schema: oryh; Owner: -
--

CREATE TABLE oryh.platform_admins (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    email text NOT NULL,
    name text,
    password_hash text NOT NULL,
    status text DEFAULT 'active'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT platform_admins_status_chk CHECK ((status = ANY (ARRAY['active'::text, 'disabled'::text])))
);


--
-- Name: platform_sessions; Type: TABLE; Schema: oryh; Owner: -
--

CREATE TABLE oryh.platform_sessions (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    platform_admin_id uuid NOT NULL,
    token_hash text NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    revoked_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: policies; Type: TABLE; Schema: oryh; Owner: -
--

CREATE TABLE oryh.policies (
    id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    code character varying(50) NOT NULL,
    version integer DEFAULT 1 NOT NULL,
    category character varying(30) NOT NULL,
    title character varying(200) NOT NULL,
    summary text,
    body text NOT NULL,
    rules_json jsonb,
    visibility character varying(20) DEFAULT 'internal'::character varying NOT NULL,
    required_capability character varying(100),
    status character varying(20) DEFAULT 'draft'::character varying NOT NULL,
    effective_from date,
    effective_thru date,
    published_at timestamp with time zone,
    published_by character varying(100),
    supersedes_id uuid,
    attachment_id uuid,
    owner_employee_id uuid,
    created_by character varying(100),
    deleted_at timestamp with time zone,
    deleted_by character varying(100),
    delete_reason text,
    custom_fields_jsonb jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT policies_effective_period_ck CHECK (((effective_thru IS NULL) OR (effective_from IS NULL) OR (effective_thru >= effective_from))),
    CONSTRAINT policies_published_attribution_ck CHECK ((((status)::text <> 'published'::text) OR ((published_at IS NOT NULL) AND (published_by IS NOT NULL)))),
    CONSTRAINT policies_restricted_needs_capability_ck CHECK ((((visibility)::text <> 'restricted'::text) OR (required_capability IS NOT NULL))),
    CONSTRAINT policies_status_ck CHECK (((status)::text = ANY ((ARRAY['draft'::character varying, 'published'::character varying, 'superseded'::character varying, 'repealed'::character varying])::text[]))),
    CONSTRAINT policies_visibility_ck CHECK (((visibility)::text = ANY ((ARRAY['internal'::character varying, 'restricted'::character varying, 'public'::character varying])::text[])))
);


--
-- Name: product_prices; Type: TABLE; Schema: oryh; Owner: -
--

CREATE TABLE oryh.product_prices (
    id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    product_id uuid NOT NULL,
    sku_id uuid,
    price_type text NOT NULL,
    price numeric(12,2) NOT NULL,
    currency character varying(3) DEFAULT 'CNY'::character varying NOT NULL,
    tax_in_price boolean DEFAULT true NOT NULL,
    tax_percentage numeric(5,2),
    status text DEFAULT 'active'::text NOT NULL,
    metadata_jsonb jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: product_skus; Type: TABLE; Schema: oryh; Owner: -
--

CREATE TABLE oryh.product_skus (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id uuid NOT NULL,
    product_id uuid NOT NULL,
    sku_code text,
    variant_attrs jsonb DEFAULT '{}'::jsonb NOT NULL,
    list_price numeric(12,2),
    status text DEFAULT 'active'::text NOT NULL,
    metadata_jsonb jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT product_skus_list_price_chk CHECK (((list_price IS NULL) OR (list_price >= (0)::numeric))),
    CONSTRAINT product_skus_status_chk CHECK ((status = ANY (ARRAY['active'::text, 'archived'::text])))
);


--
-- Name: products; Type: TABLE; Schema: oryh; Owner: -
--

CREATE TABLE oryh.products (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id uuid NOT NULL,
    product_code text,
    name text NOT NULL,
    spec text,
    unit text,
    list_price numeric(12,2),
    currency text DEFAULT 'CNY'::text NOT NULL,
    status text DEFAULT 'active'::text NOT NULL,
    metadata_jsonb jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT products_list_price_chk CHECK (((list_price IS NULL) OR (list_price >= (0)::numeric))),
    CONSTRAINT products_status_chk CHECK ((status = ANY (ARRAY['active'::text, 'archived'::text])))
);


--
-- Name: projects; Type: TABLE; Schema: oryh; Owner: -
--

CREATE TABLE oryh.projects (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id uuid NOT NULL,
    project_code text,
    project_name text NOT NULL,
    client text,
    status text DEFAULT 'active'::text NOT NULL,
    start_date date,
    end_date date,
    metadata_jsonb jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT projects_date_chk CHECK (((end_date IS NULL) OR (start_date IS NULL) OR (end_date >= start_date))),
    CONSTRAINT projects_status_chk CHECK ((status = ANY (ARRAY['active'::text, 'archived'::text])))
);


--
-- Name: purchase_order_adjustments; Type: TABLE; Schema: oryh; Owner: -
--

CREATE TABLE oryh.purchase_order_adjustments (
    id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    po_id uuid NOT NULL,
    po_item_id uuid,
    adjustment_type text NOT NULL,
    description character varying(500),
    amount numeric(12,2) NOT NULL,
    source_percentage numeric(5,2),
    metadata_jsonb jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    deleted_at timestamp with time zone
);


--
-- Name: purchase_order_items; Type: TABLE; Schema: oryh; Owner: -
--

CREATE TABLE oryh.purchase_order_items (
    id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    po_id uuid NOT NULL,
    line_no integer,
    product_id uuid,
    sku_id uuid,
    product_name_snapshot character varying(200),
    spec character varying(200),
    quantity numeric(12,2) NOT NULL,
    unit character varying(50),
    unit_price numeric(12,2),
    amount numeric(12,2),
    tax_rate numeric(5,2),
    promised_date date,
    purchase_request_item_id uuid,
    received_quantity numeric(12,2) DEFAULT 0 NOT NULL,
    attachment_id uuid,
    notes text,
    custom_fields_jsonb jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    deleted_at timestamp with time zone
);


--
-- Name: purchase_orders; Type: TABLE; Schema: oryh; Owner: -
--

CREATE TABLE oryh.purchase_orders (
    id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    po_number character varying(64) NOT NULL,
    vendor_id uuid NOT NULL,
    vendor_name_snapshot character varying(200),
    employee_id uuid NOT NULL,
    title character varying(200),
    contract_no character varying(64),
    order_date date,
    promised_date date,
    currency character varying(3) DEFAULT 'CNY'::character varying NOT NULL,
    payment_terms text,
    delivery_terms text,
    total_amount numeric(12,2),
    status text DEFAULT 'draft'::text NOT NULL,
    remarks text,
    source_report_text text,
    custom_fields_jsonb jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    deleted_at timestamp with time zone
);


--
-- Name: purchase_request_items; Type: TABLE; Schema: oryh; Owner: -
--

CREATE TABLE oryh.purchase_request_items (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id uuid NOT NULL,
    request_id uuid NOT NULL,
    product_id uuid,
    sku_id uuid,
    product_name_snapshot text,
    spec text,
    quantity numeric(12,2) NOT NULL,
    unit text,
    unit_price numeric(12,2),
    amount numeric(12,2),
    attachment_id uuid,
    notes text,
    custom_fields_jsonb jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    deleted_at timestamp with time zone,
    sales_order_item_id uuid,
    CONSTRAINT purchase_request_items_amount_chk CHECK (((amount IS NULL) OR (amount >= (0)::numeric))),
    CONSTRAINT purchase_request_items_quantity_chk CHECK ((quantity > (0)::numeric)),
    CONSTRAINT purchase_request_items_unit_price_chk CHECK (((unit_price IS NULL) OR (unit_price >= (0)::numeric)))
);


--
-- Name: purchase_requests; Type: TABLE; Schema: oryh; Owner: -
--

CREATE TABLE oryh.purchase_requests (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id uuid NOT NULL,
    employee_id uuid NOT NULL,
    title text NOT NULL,
    request_date date,
    needed_by date,
    vendor_id uuid,
    vendor_name_snapshot text,
    currency text DEFAULT 'CNY'::text NOT NULL,
    status text DEFAULT 'draft'::text NOT NULL,
    submitted_at timestamp with time zone,
    source_report_text text,
    custom_fields_jsonb jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    deleted_at timestamp with time zone,
    deleted_by text,
    delete_reason text
);


--
-- Name: resource_bookings; Type: TABLE; Schema: oryh; Owner: -
--

CREATE TABLE oryh.resource_bookings (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id uuid NOT NULL,
    resource_id uuid NOT NULL,
    booked_by_employee_id uuid NOT NULL,
    booking_type text,
    title text NOT NULL,
    start_at timestamp with time zone NOT NULL,
    end_at timestamp with time zone NOT NULL,
    quantity integer DEFAULT 1 NOT NULL,
    status text DEFAULT 'confirmed'::text NOT NULL,
    source_text text,
    notes text,
    metadata_jsonb jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    cancelled_at timestamp with time zone,
    cancelled_by text,
    cancel_reason text,
    CONSTRAINT resource_bookings_period_chk CHECK ((end_at > start_at)),
    CONSTRAINT resource_bookings_quantity_chk CHECK ((quantity >= 1)),
    CONSTRAINT resource_bookings_status_chk CHECK ((status = ANY (ARRAY['confirmed'::text, 'cancelled'::text])))
);


--
-- Name: resources; Type: TABLE; Schema: oryh; Owner: -
--

CREATE TABLE oryh.resources (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id uuid NOT NULL,
    resource_type text NOT NULL,
    name text NOT NULL,
    code text,
    location text,
    capacity integer,
    booking_mode text DEFAULT 'exclusive'::text NOT NULL,
    max_quantity integer,
    status text DEFAULT 'active'::text NOT NULL,
    metadata_jsonb jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT resources_booking_mode_chk CHECK ((booking_mode = ANY (ARRAY['exclusive'::text, 'shared'::text]))),
    CONSTRAINT resources_capacity_chk CHECK (((capacity IS NULL) OR (capacity >= 1))),
    CONSTRAINT resources_max_quantity_chk CHECK (((max_quantity IS NULL) OR (max_quantity >= 1))),
    CONSTRAINT resources_status_chk CHECK ((status = ANY (ARRAY['active'::text, 'inactive'::text, 'archived'::text])))
);


--
-- Name: roles; Type: TABLE; Schema: oryh; Owner: -
--

CREATE TABLE oryh.roles (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id uuid NOT NULL,
    name text NOT NULL,
    title text,
    description text,
    permissions_jsonb jsonb DEFAULT '[]'::jsonb NOT NULL,
    is_system boolean DEFAULT false NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: sales_order_adjustments; Type: TABLE; Schema: oryh; Owner: -
--

CREATE TABLE oryh.sales_order_adjustments (
    id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    order_id uuid NOT NULL,
    order_item_id uuid,
    adjustment_type text NOT NULL,
    description character varying(500),
    amount numeric(12,2) NOT NULL,
    source_percentage numeric(5,2),
    metadata_jsonb jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    deleted_at timestamp with time zone
);


--
-- Name: sales_order_items; Type: TABLE; Schema: oryh; Owner: -
--

CREATE TABLE oryh.sales_order_items (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id uuid NOT NULL,
    order_id uuid NOT NULL,
    line_no integer,
    product_id uuid,
    sku_id uuid,
    product_name_snapshot text,
    spec text,
    quantity numeric(12,2) NOT NULL,
    unit text,
    list_price_snapshot numeric(12,2),
    unit_price numeric(12,2),
    amount numeric(12,2),
    tax_rate numeric(5,2),
    is_gift boolean DEFAULT false NOT NULL,
    promised_date date,
    attachment_id uuid,
    notes text,
    custom_fields_jsonb jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    deleted_at timestamp with time zone,
    CONSTRAINT sales_order_items_amount_chk CHECK (((amount IS NULL) OR (amount >= (0)::numeric))),
    CONSTRAINT sales_order_items_list_price_chk CHECK (((list_price_snapshot IS NULL) OR (list_price_snapshot >= (0)::numeric))),
    CONSTRAINT sales_order_items_quantity_chk CHECK ((quantity > (0)::numeric)),
    CONSTRAINT sales_order_items_tax_rate_chk CHECK (((tax_rate IS NULL) OR ((tax_rate >= (0)::numeric) AND (tax_rate <= (100)::numeric)))),
    CONSTRAINT sales_order_items_unit_price_chk CHECK (((unit_price IS NULL) OR (unit_price >= (0)::numeric)))
);


--
-- Name: sales_orders; Type: TABLE; Schema: oryh; Owner: -
--

CREATE TABLE oryh.sales_orders (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id uuid NOT NULL,
    order_no text NOT NULL,
    quotation_id uuid,
    source_quote_number text,
    employee_id uuid NOT NULL,
    customer_id uuid,
    customer_name_snapshot text,
    contact_name text,
    contact_phone text,
    ship_to_address text,
    title text NOT NULL,
    project_id uuid,
    contract_no text,
    order_date date,
    promised_date date,
    currency text DEFAULT 'CNY'::text NOT NULL,
    payment_terms text,
    delivery_terms text,
    total_amount numeric(12,2),
    status text DEFAULT 'draft'::text NOT NULL,
    submitted_at timestamp with time zone,
    shipped_at timestamp with time zone,
    signed_at timestamp with time zone,
    logistics_company text,
    logistics_tracking_no text,
    remarks text,
    source_report_text text,
    custom_fields_jsonb jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    deleted_at timestamp with time zone,
    deleted_by text,
    delete_reason text,
    CONSTRAINT sales_orders_total_amount_chk CHECK (((total_amount IS NULL) OR (total_amount >= (0)::numeric)))
);


--
-- Name: sales_quotation_adjustments; Type: TABLE; Schema: oryh; Owner: -
--

CREATE TABLE oryh.sales_quotation_adjustments (
    id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    quotation_id uuid NOT NULL,
    quotation_item_id uuid,
    adjustment_type text NOT NULL,
    description character varying(500),
    amount numeric(12,2) NOT NULL,
    source_percentage numeric(5,2),
    metadata_jsonb jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    deleted_at timestamp with time zone
);


--
-- Name: sales_quotation_items; Type: TABLE; Schema: oryh; Owner: -
--

CREATE TABLE oryh.sales_quotation_items (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id uuid NOT NULL,
    quotation_id uuid NOT NULL,
    line_no integer,
    product_id uuid,
    sku_id uuid,
    product_name_snapshot text,
    spec text,
    quantity numeric(12,2) NOT NULL,
    unit text,
    list_price_snapshot numeric(12,2),
    unit_price numeric(12,2),
    amount numeric(12,2),
    tax_rate numeric(5,2),
    is_gift boolean DEFAULT false NOT NULL,
    lead_time text,
    attachment_id uuid,
    notes text,
    custom_fields_jsonb jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    deleted_at timestamp with time zone,
    CONSTRAINT sales_quotation_items_amount_chk CHECK (((amount IS NULL) OR (amount >= (0)::numeric))),
    CONSTRAINT sales_quotation_items_list_price_chk CHECK (((list_price_snapshot IS NULL) OR (list_price_snapshot >= (0)::numeric))),
    CONSTRAINT sales_quotation_items_quantity_chk CHECK ((quantity > (0)::numeric)),
    CONSTRAINT sales_quotation_items_tax_rate_chk CHECK (((tax_rate IS NULL) OR ((tax_rate >= (0)::numeric) AND (tax_rate <= (100)::numeric)))),
    CONSTRAINT sales_quotation_items_unit_price_chk CHECK (((unit_price IS NULL) OR (unit_price >= (0)::numeric)))
);


--
-- Name: sales_quotations; Type: TABLE; Schema: oryh; Owner: -
--

CREATE TABLE oryh.sales_quotations (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id uuid NOT NULL,
    quote_number text NOT NULL,
    revision_no integer DEFAULT 1 NOT NULL,
    revision_of_id uuid,
    employee_id uuid NOT NULL,
    customer_id uuid,
    customer_name_snapshot text,
    contact_name text,
    contact_phone text,
    contact_email text,
    title text NOT NULL,
    project_id uuid,
    quote_date date,
    valid_until date,
    currency text DEFAULT 'CNY'::text NOT NULL,
    payment_terms text,
    delivery_terms text,
    total_amount numeric(12,2),
    status text DEFAULT 'draft'::text NOT NULL,
    submitted_at timestamp with time zone,
    sent_at timestamp with time zone,
    closed_at timestamp with time zone,
    outcome_note text,
    remarks text,
    source_report_text text,
    custom_fields_jsonb jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    deleted_at timestamp with time zone,
    deleted_by text,
    delete_reason text,
    CONSTRAINT sales_quotations_revision_no_chk CHECK ((revision_no >= 1)),
    CONSTRAINT sales_quotations_total_amount_chk CHECK (((total_amount IS NULL) OR (total_amount >= (0)::numeric)))
);


--
-- Name: supplier_products; Type: TABLE; Schema: oryh; Owner: -
--

CREATE TABLE oryh.supplier_products (
    id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    product_id uuid NOT NULL,
    vendor_id uuid NOT NULL,
    supplier_product_code character varying(64),
    supplier_product_name character varying(200),
    last_price numeric(12,2),
    currency character varying(3) DEFAULT 'CNY'::character varying NOT NULL,
    lead_time_days integer,
    min_order_quantity numeric(12,2),
    order_increment numeric(12,2),
    preference integer,
    status text DEFAULT 'active'::text NOT NULL,
    metadata_jsonb jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: tenant_skill_assignments; Type: TABLE; Schema: oryh; Owner: -
--

CREATE TABLE oryh.tenant_skill_assignments (
    id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    skill_id uuid NOT NULL,
    subject_type character varying(20) NOT NULL,
    subject_id character varying(100) NOT NULL,
    created_by character varying(100),
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: tenant_skills; Type: TABLE; Schema: oryh; Owner: -
--

CREATE TABLE oryh.tenant_skills (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id uuid NOT NULL,
    name text NOT NULL,
    title text,
    description text,
    files_jsonb jsonb DEFAULT '{}'::jsonb NOT NULL,
    version integer DEFAULT 1 NOT NULL,
    status text DEFAULT 'active'::text NOT NULL,
    created_by text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    kind text DEFAULT 'custom'::text NOT NULL,
    required_capability text,
    catalog_required_capability text,
    distribution_mode character varying(20) DEFAULT 'capability'::character varying NOT NULL,
    CONSTRAINT tenant_skills_kind_chk CHECK ((kind = ANY (ARRAY['product'::text, 'custom'::text]))),
    CONSTRAINT tenant_skills_status_chk CHECK ((status = ANY (ARRAY['active'::text, 'archived'::text]))),
    CONSTRAINT tenant_skills_version_chk CHECK ((version >= 1))
);


--
-- Name: tenants; Type: TABLE; Schema: oryh; Owner: -
--

CREATE TABLE oryh.tenants (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    name text NOT NULL,
    status text DEFAULT 'active'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    email_domain text,
    slug character varying(24),
    CONSTRAINT tenants_status_chk CHECK ((status = ANY (ARRAY['active'::text, 'inactive'::text])))
);


--
-- Name: timesheet_entries; Type: TABLE; Schema: oryh; Owner: -
--

CREATE TABLE oryh.timesheet_entries (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id uuid NOT NULL,
    header_id uuid NOT NULL,
    employee_id uuid NOT NULL,
    work_date date NOT NULL,
    project_id uuid,
    project_name_snapshot text,
    client text,
    task text,
    hours numeric(5,2) NOT NULL,
    work_type text DEFAULT 'regular'::text NOT NULL,
    notes text,
    custom_fields_jsonb jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    deleted_at timestamp with time zone,
    CONSTRAINT timesheet_entries_hours_chk CHECK (((hours > (0)::numeric) AND (hours <= (24)::numeric))),
    CONSTRAINT timesheet_entries_work_type_chk CHECK ((work_type = ANY (ARRAY['regular'::text, 'overtime'::text, 'holiday'::text, 'travel'::text, 'other'::text])))
);


--
-- Name: timesheet_headers; Type: TABLE; Schema: oryh; Owner: -
--

CREATE TABLE oryh.timesheet_headers (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id uuid NOT NULL,
    employee_id uuid NOT NULL,
    period_start date NOT NULL,
    period_end date NOT NULL,
    status text DEFAULT 'draft'::text NOT NULL,
    submitted_at timestamp with time zone,
    source_report_text text,
    custom_fields_jsonb jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    deleted_at timestamp with time zone,
    deleted_by text,
    delete_reason text,
    CONSTRAINT timesheet_headers_period_chk CHECK ((period_end >= period_start))
);


--
-- Name: todos; Type: TABLE; Schema: oryh; Owner: -
--

CREATE TABLE oryh.todos (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id uuid NOT NULL,
    employee_id uuid NOT NULL,
    entity_type text NOT NULL,
    entity_id uuid NOT NULL,
    title text NOT NULL,
    description text,
    status text DEFAULT 'open'::text NOT NULL,
    metadata_jsonb jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    completed_at timestamp with time zone,
    completed_by text,
    todo_type text,
    created_by text,
    due_at timestamp with time zone,
    CONSTRAINT todos_entity_type_chk CHECK ((entity_type = ANY (ARRAY['timesheet_header'::text, 'expense_claim'::text, 'purchase_request'::text, 'sales_quotation'::text, 'sales_order'::text, 'project'::text, 'approval_target'::text, 'business_object'::text]))),
    CONSTRAINT todos_status_chk CHECK ((status = ANY (ARRAY['open'::text, 'completed'::text])))
);


--
-- Name: type_options; Type: TABLE; Schema: oryh; Owner: -
--

CREATE TABLE oryh.type_options (
    id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    family character varying(50) NOT NULL,
    name character varying(50) NOT NULL,
    kind character varying(20) DEFAULT 'custom'::character varying NOT NULL,
    title character varying(200),
    description text,
    status character varying(20) DEFAULT 'active'::character varying NOT NULL,
    created_by character varying(100),
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    sign integer
);


--
-- Name: user_sessions; Type: TABLE; Schema: oryh; Owner: -
--

CREATE TABLE oryh.user_sessions (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    token_hash text NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    revoked_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: users; Type: TABLE; Schema: oryh; Owner: -
--

CREATE TABLE oryh.users (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id uuid NOT NULL,
    email text NOT NULL,
    name text,
    password_hash text,
    oidc_subject text,
    role text DEFAULT 'member'::text NOT NULL,
    employee_id uuid,
    status text DEFAULT 'active'::text NOT NULL,
    email_verified_at timestamp with time zone,
    invite_token_hash text,
    invite_expires_at timestamp with time zone,
    invited_by uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT users_status_chk CHECK ((status = ANY (ARRAY['invited'::text, 'active'::text, 'disabled'::text])))
);


--
-- Name: vendors; Type: TABLE; Schema: oryh; Owner: -
--

CREATE TABLE oryh.vendors (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id uuid NOT NULL,
    vendor_code text,
    name text NOT NULL,
    tax_id text,
    contact text,
    email text,
    phone text,
    status text DEFAULT 'active'::text NOT NULL,
    metadata_jsonb jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT vendors_status_chk CHECK ((status = ANY (ARRAY['active'::text, 'archived'::text])))
);


--
-- Name: workflow_definitions; Type: TABLE; Schema: oryh; Owner: -
--

CREATE TABLE oryh.workflow_definitions (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id uuid NOT NULL,
    entity_kind text DEFAULT 'business_object'::text NOT NULL,
    object_type text NOT NULL,
    name text DEFAULT 'default'::text NOT NULL,
    version integer DEFAULT 1 NOT NULL,
    definition_text text NOT NULL,
    status text DEFAULT 'active'::text NOT NULL,
    created_by text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT workflow_definitions_entity_kind_chk CHECK ((entity_kind = ANY (ARRAY['business_object'::text, 'builtin'::text]))),
    CONSTRAINT workflow_definitions_status_chk CHECK ((status = ANY (ARRAY['active'::text, 'superseded'::text]))),
    CONSTRAINT workflow_definitions_version_chk CHECK ((version >= 1))
);


--
-- Name: audit_logs id; Type: DEFAULT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.audit_logs ALTER COLUMN id SET DEFAULT nextval('oryh.audit_logs_id_seq'::regclass);


--
-- Name: alembic_version alembic_version_pkc; Type: CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.alembic_version
    ADD CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num);


--
-- Name: api_keys api_keys_pkey; Type: CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.api_keys
    ADD CONSTRAINT api_keys_pkey PRIMARY KEY (id);


--
-- Name: approval_records approval_records_action_uk; Type: CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.approval_records
    ADD CONSTRAINT approval_records_action_uk UNIQUE (tenant_id, entity_type, entity_id, round_no, sequence_no, action);


--
-- Name: approval_records approval_records_pkey; Type: CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.approval_records
    ADD CONSTRAINT approval_records_pkey PRIMARY KEY (id);


--
-- Name: business_objects approval_targets_pkey; Type: CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.business_objects
    ADD CONSTRAINT approval_targets_pkey PRIMARY KEY (id);


--
-- Name: attachments attachments_pkey; Type: CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.attachments
    ADD CONSTRAINT attachments_pkey PRIMARY KEY (id);


--
-- Name: attachments attachments_tenant_sha256_uk; Type: CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.attachments
    ADD CONSTRAINT attachments_tenant_sha256_uk UNIQUE (tenant_id, sha256);


--
-- Name: audit_logs audit_logs_pkey; Type: CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.audit_logs
    ADD CONSTRAINT audit_logs_pkey PRIMARY KEY (id);


--
-- Name: billing_account_entries billing_account_entries_pkey; Type: CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.billing_account_entries
    ADD CONSTRAINT billing_account_entries_pkey PRIMARY KEY (id);


--
-- Name: billing_accounts billing_accounts_code_uk; Type: CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.billing_accounts
    ADD CONSTRAINT billing_accounts_code_uk UNIQUE (tenant_id, account_code);


--
-- Name: billing_accounts billing_accounts_pkey; Type: CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.billing_accounts
    ADD CONSTRAINT billing_accounts_pkey PRIMARY KEY (id);


--
-- Name: business_object_links business_object_links_pkey; Type: CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.business_object_links
    ADD CONSTRAINT business_object_links_pkey PRIMARY KEY (id);


--
-- Name: business_object_links business_object_links_unique_link; Type: CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.business_object_links
    ADD CONSTRAINT business_object_links_unique_link UNIQUE (tenant_id, source_object_id, target_object_id, link_type);


--
-- Name: capabilities capabilities_pkey; Type: CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.capabilities
    ADD CONSTRAINT capabilities_pkey PRIMARY KEY (id);


--
-- Name: capabilities capabilities_tenant_name_uk; Type: CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.capabilities
    ADD CONSTRAINT capabilities_tenant_name_uk UNIQUE (tenant_id, name);


--
-- Name: customers customers_pkey; Type: CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.customers
    ADD CONSTRAINT customers_pkey PRIMARY KEY (id);


--
-- Name: device_authorizations device_authorizations_device_code_hash_key; Type: CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.device_authorizations
    ADD CONSTRAINT device_authorizations_device_code_hash_key UNIQUE (device_code_hash);


--
-- Name: device_authorizations device_authorizations_pkey; Type: CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.device_authorizations
    ADD CONSTRAINT device_authorizations_pkey PRIMARY KEY (id);


--
-- Name: employees employees_pkey; Type: CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.employees
    ADD CONSTRAINT employees_pkey PRIMARY KEY (id);


--
-- Name: enterprise_pilot_applications enterprise_pilot_applications_email_uk; Type: CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.enterprise_pilot_applications
    ADD CONSTRAINT enterprise_pilot_applications_email_uk UNIQUE (email);


--
-- Name: enterprise_pilot_applications enterprise_pilot_applications_pkey; Type: CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.enterprise_pilot_applications
    ADD CONSTRAINT enterprise_pilot_applications_pkey PRIMARY KEY (id);


--
-- Name: expense_claims expense_claims_pkey; Type: CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.expense_claims
    ADD CONSTRAINT expense_claims_pkey PRIMARY KEY (id);


--
-- Name: expense_items expense_items_pkey; Type: CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.expense_items
    ADD CONSTRAINT expense_items_pkey PRIMARY KEY (id);


--
-- Name: flow_runs flow_runs_pkey; Type: CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.flow_runs
    ADD CONSTRAINT flow_runs_pkey PRIMARY KEY (id);


--
-- Name: flow_subscriptions flow_subscriptions_entity_uk; Type: CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.flow_subscriptions
    ADD CONSTRAINT flow_subscriptions_entity_uk UNIQUE (tenant_id, entity_type);


--
-- Name: flow_subscriptions flow_subscriptions_pkey; Type: CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.flow_subscriptions
    ADD CONSTRAINT flow_subscriptions_pkey PRIMARY KEY (id);


--
-- Name: inventory_item_details inventory_item_details_pkey; Type: CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.inventory_item_details
    ADD CONSTRAINT inventory_item_details_pkey PRIMARY KEY (id);


--
-- Name: inventory_items inventory_items_pkey; Type: CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.inventory_items
    ADD CONSTRAINT inventory_items_pkey PRIMARY KEY (id);


--
-- Name: invoice_items invoice_items_pkey; Type: CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.invoice_items
    ADD CONSTRAINT invoice_items_pkey PRIMARY KEY (id);


--
-- Name: invoices invoices_invoice_no_uk; Type: CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.invoices
    ADD CONSTRAINT invoices_invoice_no_uk UNIQUE (tenant_id, invoice_no);


--
-- Name: invoices invoices_pkey; Type: CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.invoices
    ADD CONSTRAINT invoices_pkey PRIMARY KEY (id);


--
-- Name: object_type_definitions object_type_definitions_pkey; Type: CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.object_type_definitions
    ADD CONSTRAINT object_type_definitions_pkey PRIMARY KEY (id);


--
-- Name: object_type_definitions object_type_definitions_tenant_kind_type_uk; Type: CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.object_type_definitions
    ADD CONSTRAINT object_type_definitions_tenant_kind_type_uk UNIQUE (tenant_id, entity_kind, object_type);


--
-- Name: pay_histories pay_histories_pkey; Type: CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.pay_histories
    ADD CONSTRAINT pay_histories_pkey PRIMARY KEY (id);


--
-- Name: payment_applications payment_applications_pkey; Type: CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.payment_applications
    ADD CONSTRAINT payment_applications_pkey PRIMARY KEY (id);


--
-- Name: payments payments_payment_no_uk; Type: CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.payments
    ADD CONSTRAINT payments_payment_no_uk UNIQUE (tenant_id, payment_no);


--
-- Name: payments payments_pkey; Type: CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.payments
    ADD CONSTRAINT payments_pkey PRIMARY KEY (id);


--
-- Name: pending_registrations pending_registrations_pkey; Type: CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.pending_registrations
    ADD CONSTRAINT pending_registrations_pkey PRIMARY KEY (id);


--
-- Name: pending_registrations pending_registrations_token_hash_key; Type: CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.pending_registrations
    ADD CONSTRAINT pending_registrations_token_hash_key UNIQUE (token_hash);


--
-- Name: platform_admins platform_admins_email_key; Type: CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.platform_admins
    ADD CONSTRAINT platform_admins_email_key UNIQUE (email);


--
-- Name: platform_admins platform_admins_pkey; Type: CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.platform_admins
    ADD CONSTRAINT platform_admins_pkey PRIMARY KEY (id);


--
-- Name: platform_sessions platform_sessions_pkey; Type: CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.platform_sessions
    ADD CONSTRAINT platform_sessions_pkey PRIMARY KEY (id);


--
-- Name: platform_sessions platform_sessions_token_hash_key; Type: CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.platform_sessions
    ADD CONSTRAINT platform_sessions_token_hash_key UNIQUE (token_hash);


--
-- Name: policies policies_pkey; Type: CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.policies
    ADD CONSTRAINT policies_pkey PRIMARY KEY (id);


--
-- Name: policies policies_version_uk; Type: CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.policies
    ADD CONSTRAINT policies_version_uk UNIQUE (tenant_id, code, version);


--
-- Name: product_prices product_prices_pkey; Type: CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.product_prices
    ADD CONSTRAINT product_prices_pkey PRIMARY KEY (id);


--
-- Name: product_skus product_skus_pkey; Type: CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.product_skus
    ADD CONSTRAINT product_skus_pkey PRIMARY KEY (id);


--
-- Name: products products_pkey; Type: CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.products
    ADD CONSTRAINT products_pkey PRIMARY KEY (id);


--
-- Name: projects projects_pkey; Type: CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.projects
    ADD CONSTRAINT projects_pkey PRIMARY KEY (id);


--
-- Name: purchase_order_adjustments purchase_order_adjustments_pkey; Type: CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.purchase_order_adjustments
    ADD CONSTRAINT purchase_order_adjustments_pkey PRIMARY KEY (id);


--
-- Name: purchase_order_items purchase_order_items_pkey; Type: CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.purchase_order_items
    ADD CONSTRAINT purchase_order_items_pkey PRIMARY KEY (id);


--
-- Name: purchase_orders purchase_orders_pkey; Type: CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.purchase_orders
    ADD CONSTRAINT purchase_orders_pkey PRIMARY KEY (id);


--
-- Name: purchase_orders purchase_orders_po_number_uk; Type: CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.purchase_orders
    ADD CONSTRAINT purchase_orders_po_number_uk UNIQUE (tenant_id, po_number);


--
-- Name: purchase_request_items purchase_request_items_pkey; Type: CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.purchase_request_items
    ADD CONSTRAINT purchase_request_items_pkey PRIMARY KEY (id);


--
-- Name: purchase_requests purchase_requests_pkey; Type: CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.purchase_requests
    ADD CONSTRAINT purchase_requests_pkey PRIMARY KEY (id);


--
-- Name: resource_bookings resource_bookings_pkey; Type: CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.resource_bookings
    ADD CONSTRAINT resource_bookings_pkey PRIMARY KEY (id);


--
-- Name: resources resources_pkey; Type: CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.resources
    ADD CONSTRAINT resources_pkey PRIMARY KEY (id);


--
-- Name: roles roles_pkey; Type: CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.roles
    ADD CONSTRAINT roles_pkey PRIMARY KEY (id);


--
-- Name: roles roles_tenant_name_uk; Type: CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.roles
    ADD CONSTRAINT roles_tenant_name_uk UNIQUE (tenant_id, name);


--
-- Name: sales_order_adjustments sales_order_adjustments_pkey; Type: CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.sales_order_adjustments
    ADD CONSTRAINT sales_order_adjustments_pkey PRIMARY KEY (id);


--
-- Name: sales_order_items sales_order_items_pkey; Type: CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.sales_order_items
    ADD CONSTRAINT sales_order_items_pkey PRIMARY KEY (id);


--
-- Name: sales_orders sales_orders_order_no_uk; Type: CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.sales_orders
    ADD CONSTRAINT sales_orders_order_no_uk UNIQUE (tenant_id, order_no);


--
-- Name: sales_orders sales_orders_pkey; Type: CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.sales_orders
    ADD CONSTRAINT sales_orders_pkey PRIMARY KEY (id);


--
-- Name: sales_quotation_adjustments sales_quotation_adjustments_pkey; Type: CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.sales_quotation_adjustments
    ADD CONSTRAINT sales_quotation_adjustments_pkey PRIMARY KEY (id);


--
-- Name: sales_quotation_items sales_quotation_items_pkey; Type: CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.sales_quotation_items
    ADD CONSTRAINT sales_quotation_items_pkey PRIMARY KEY (id);


--
-- Name: sales_quotations sales_quotations_number_rev_uk; Type: CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.sales_quotations
    ADD CONSTRAINT sales_quotations_number_rev_uk UNIQUE (tenant_id, quote_number, revision_no);


--
-- Name: sales_quotations sales_quotations_pkey; Type: CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.sales_quotations
    ADD CONSTRAINT sales_quotations_pkey PRIMARY KEY (id);


--
-- Name: supplier_products supplier_products_pkey; Type: CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.supplier_products
    ADD CONSTRAINT supplier_products_pkey PRIMARY KEY (id);


--
-- Name: supplier_products supplier_products_tenant_product_vendor_uk; Type: CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.supplier_products
    ADD CONSTRAINT supplier_products_tenant_product_vendor_uk UNIQUE (tenant_id, product_id, vendor_id);


--
-- Name: tenant_skill_assignments tenant_skill_assignments_pkey; Type: CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.tenant_skill_assignments
    ADD CONSTRAINT tenant_skill_assignments_pkey PRIMARY KEY (id);


--
-- Name: tenant_skill_assignments tenant_skill_assignments_uk; Type: CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.tenant_skill_assignments
    ADD CONSTRAINT tenant_skill_assignments_uk UNIQUE (tenant_id, skill_id, subject_type, subject_id);


--
-- Name: tenant_skills tenant_skills_pkey; Type: CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.tenant_skills
    ADD CONSTRAINT tenant_skills_pkey PRIMARY KEY (id);


--
-- Name: tenant_skills tenant_skills_tenant_name_uk; Type: CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.tenant_skills
    ADD CONSTRAINT tenant_skills_tenant_name_uk UNIQUE (tenant_id, name);


--
-- Name: tenants tenants_email_domain_key; Type: CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.tenants
    ADD CONSTRAINT tenants_email_domain_key UNIQUE (email_domain);


--
-- Name: tenants tenants_pkey; Type: CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.tenants
    ADD CONSTRAINT tenants_pkey PRIMARY KEY (id);


--
-- Name: timesheet_entries timesheet_entries_pkey; Type: CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.timesheet_entries
    ADD CONSTRAINT timesheet_entries_pkey PRIMARY KEY (id);


--
-- Name: timesheet_headers timesheet_headers_pkey; Type: CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.timesheet_headers
    ADD CONSTRAINT timesheet_headers_pkey PRIMARY KEY (id);


--
-- Name: todos todos_pkey; Type: CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.todos
    ADD CONSTRAINT todos_pkey PRIMARY KEY (id);


--
-- Name: type_options type_options_pkey; Type: CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.type_options
    ADD CONSTRAINT type_options_pkey PRIMARY KEY (id);


--
-- Name: type_options type_options_tenant_family_name_uk; Type: CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.type_options
    ADD CONSTRAINT type_options_tenant_family_name_uk UNIQUE (tenant_id, family, name);


--
-- Name: user_sessions user_sessions_pkey; Type: CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.user_sessions
    ADD CONSTRAINT user_sessions_pkey PRIMARY KEY (id);


--
-- Name: user_sessions user_sessions_token_hash_key; Type: CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.user_sessions
    ADD CONSTRAINT user_sessions_token_hash_key UNIQUE (token_hash);


--
-- Name: users users_email_key; Type: CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.users
    ADD CONSTRAINT users_email_key UNIQUE (email);


--
-- Name: users users_employee_id_key; Type: CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.users
    ADD CONSTRAINT users_employee_id_key UNIQUE (employee_id);


--
-- Name: users users_invite_token_hash_key; Type: CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.users
    ADD CONSTRAINT users_invite_token_hash_key UNIQUE (invite_token_hash);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- Name: vendors vendors_pkey; Type: CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.vendors
    ADD CONSTRAINT vendors_pkey PRIMARY KEY (id);


--
-- Name: workflow_definitions workflow_definitions_pkey; Type: CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.workflow_definitions
    ADD CONSTRAINT workflow_definitions_pkey PRIMARY KEY (id);


--
-- Name: workflow_definitions workflow_definitions_version_uk; Type: CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.workflow_definitions
    ADD CONSTRAINT workflow_definitions_version_uk UNIQUE (tenant_id, entity_kind, object_type, name, version);


--
-- Name: api_keys_key_hash_uk; Type: INDEX; Schema: oryh; Owner: -
--

CREATE UNIQUE INDEX api_keys_key_hash_uk ON oryh.api_keys USING btree (key_hash);


--
-- Name: api_keys_tenant_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX api_keys_tenant_idx ON oryh.api_keys USING btree (tenant_id);


--
-- Name: api_keys_user_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX api_keys_user_idx ON oryh.api_keys USING btree (user_id);


--
-- Name: attachments_tenant_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX attachments_tenant_idx ON oryh.attachments USING btree (tenant_id);


--
-- Name: audit_logs_tenant_entity_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX audit_logs_tenant_entity_idx ON oryh.audit_logs USING btree (tenant_id, entity_type, entity_id, id DESC);


--
-- Name: audit_logs_tenant_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX audit_logs_tenant_idx ON oryh.audit_logs USING btree (tenant_id, id DESC);


--
-- Name: billing_account_entries_account_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX billing_account_entries_account_idx ON oryh.billing_account_entries USING btree (billing_account_id);


--
-- Name: billing_account_entries_entity_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX billing_account_entries_entity_idx ON oryh.billing_account_entries USING btree (entity_id);


--
-- Name: billing_account_entries_expiry_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX billing_account_entries_expiry_idx ON oryh.billing_account_entries USING btree (tenant_id, billing_account_id, expires_at);


--
-- Name: billing_account_entries_idempotency_uk; Type: INDEX; Schema: oryh; Owner: -
--

CREATE UNIQUE INDEX billing_account_entries_idempotency_uk ON oryh.billing_account_entries USING btree (tenant_id, billing_account_id, idempotency_key, idempotency_seq) WHERE (idempotency_key IS NOT NULL);


--
-- Name: billing_account_entries_reason_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX billing_account_entries_reason_idx ON oryh.billing_account_entries USING btree (reason);


--
-- Name: billing_account_entries_source_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX billing_account_entries_source_idx ON oryh.billing_account_entries USING btree (tenant_id, entity_type, entity_id);


--
-- Name: billing_account_entries_tenant_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX billing_account_entries_tenant_idx ON oryh.billing_account_entries USING btree (tenant_id);


--
-- Name: billing_accounts_customer_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX billing_accounts_customer_idx ON oryh.billing_accounts USING btree (customer_id);


--
-- Name: billing_accounts_employee_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX billing_accounts_employee_idx ON oryh.billing_accounts USING btree (employee_id);


--
-- Name: billing_accounts_external_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX billing_accounts_external_idx ON oryh.billing_accounts USING btree (external_account_id);


--
-- Name: billing_accounts_tenant_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX billing_accounts_tenant_idx ON oryh.billing_accounts USING btree (tenant_id);


--
-- Name: billing_accounts_unit_type_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX billing_accounts_unit_type_idx ON oryh.billing_accounts USING btree (tenant_id, unit_type);


--
-- Name: billing_accounts_vendor_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX billing_accounts_vendor_idx ON oryh.billing_accounts USING btree (vendor_id);


--
-- Name: business_object_links_tenant_source_type_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX business_object_links_tenant_source_type_idx ON oryh.business_object_links USING btree (tenant_id, source_object_id, link_type, created_at DESC);


--
-- Name: business_object_links_tenant_target_type_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX business_object_links_tenant_target_type_idx ON oryh.business_object_links USING btree (tenant_id, target_object_id, link_type, created_at DESC);


--
-- Name: business_objects_payload_gin_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX business_objects_payload_gin_idx ON oryh.business_objects USING gin (payload_jsonb jsonb_path_ops);


--
-- Name: business_objects_tenant_status_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX business_objects_tenant_status_idx ON oryh.business_objects USING btree (tenant_id, status, created_at DESC) WHERE (deleted_at IS NULL);


--
-- Name: capabilities_tenant_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX capabilities_tenant_idx ON oryh.capabilities USING btree (tenant_id);


--
-- Name: customers_tax_id_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX customers_tax_id_idx ON oryh.customers USING btree (tenant_id, tax_id);


--
-- Name: customers_tenant_code_uq; Type: INDEX; Schema: oryh; Owner: -
--

CREATE UNIQUE INDEX customers_tenant_code_uq ON oryh.customers USING btree (tenant_id, customer_code) WHERE (customer_code IS NOT NULL);


--
-- Name: customers_tenant_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX customers_tenant_idx ON oryh.customers USING btree (tenant_id, status, created_at DESC);


--
-- Name: customers_tenant_phone_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX customers_tenant_phone_idx ON oryh.customers USING btree (tenant_id, phone);


--
-- Name: device_authorizations_user_code_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX device_authorizations_user_code_idx ON oryh.device_authorizations USING btree (user_code);


--
-- Name: employees_tenant_employee_code_uk; Type: INDEX; Schema: oryh; Owner: -
--

CREATE UNIQUE INDEX employees_tenant_employee_code_uk ON oryh.employees USING btree (tenant_id, employee_code) WHERE (employee_code IS NOT NULL);


--
-- Name: enterprise_pilot_applications_domain_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX enterprise_pilot_applications_domain_idx ON oryh.enterprise_pilot_applications USING btree (email_domain);


--
-- Name: enterprise_pilot_applications_status_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX enterprise_pilot_applications_status_idx ON oryh.enterprise_pilot_applications USING btree (status);


--
-- Name: expense_claims_employee_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX expense_claims_employee_idx ON oryh.expense_claims USING btree (employee_id);


--
-- Name: expense_claims_tenant_status_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX expense_claims_tenant_status_idx ON oryh.expense_claims USING btree (tenant_id, status, created_at DESC);


--
-- Name: expense_items_claim_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX expense_items_claim_idx ON oryh.expense_items USING btree (claim_id);


--
-- Name: expense_items_tenant_invoice_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX expense_items_tenant_invoice_idx ON oryh.expense_items USING btree (tenant_id, invoice_number) WHERE (invoice_number IS NOT NULL);


--
-- Name: flow_runs_open_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX flow_runs_open_idx ON oryh.flow_runs USING btree (tenant_id, entity_type) WHERE ((status)::text = 'running'::text);


--
-- Name: flow_runs_subscription_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX flow_runs_subscription_idx ON oryh.flow_runs USING btree (subscription_id);


--
-- Name: flow_runs_tenant_started_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX flow_runs_tenant_started_idx ON oryh.flow_runs USING btree (tenant_id, started_at DESC);


--
-- Name: flow_subscriptions_parked_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX flow_subscriptions_parked_idx ON oryh.flow_subscriptions USING btree (tenant_id, entity_type) WHERE (parked_at IS NOT NULL);


--
-- Name: flow_subscriptions_tenant_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX flow_subscriptions_tenant_idx ON oryh.flow_subscriptions USING btree (tenant_id);


--
-- Name: inventory_item_details_item_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX inventory_item_details_item_idx ON oryh.inventory_item_details USING btree (inventory_item_id);


--
-- Name: inventory_item_details_tenant_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX inventory_item_details_tenant_idx ON oryh.inventory_item_details USING btree (tenant_id);


--
-- Name: inventory_items_product_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX inventory_items_product_idx ON oryh.inventory_items USING btree (product_id);


--
-- Name: inventory_items_product_tuple_uq; Type: INDEX; Schema: oryh; Owner: -
--

CREATE UNIQUE INDEX inventory_items_product_tuple_uq ON oryh.inventory_items USING btree (tenant_id, product_id, facility, lot_id) WHERE (sku_id IS NULL);


--
-- Name: inventory_items_sku_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX inventory_items_sku_idx ON oryh.inventory_items USING btree (sku_id);


--
-- Name: inventory_items_sku_tuple_uq; Type: INDEX; Schema: oryh; Owner: -
--

CREATE UNIQUE INDEX inventory_items_sku_tuple_uq ON oryh.inventory_items USING btree (tenant_id, sku_id, facility, lot_id) WHERE (sku_id IS NOT NULL);


--
-- Name: inventory_items_tenant_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX inventory_items_tenant_idx ON oryh.inventory_items USING btree (tenant_id);


--
-- Name: invoice_items_invoice_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX invoice_items_invoice_idx ON oryh.invoice_items USING btree (invoice_id);


--
-- Name: invoice_items_pay_history_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX invoice_items_pay_history_idx ON oryh.invoice_items USING btree (pay_history_id);


--
-- Name: invoice_items_purchase_order_item_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX invoice_items_purchase_order_item_idx ON oryh.invoice_items USING btree (purchase_order_item_id);


--
-- Name: invoice_items_sales_order_item_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX invoice_items_sales_order_item_idx ON oryh.invoice_items USING btree (sales_order_item_id);


--
-- Name: invoice_items_tenant_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX invoice_items_tenant_idx ON oryh.invoice_items USING btree (tenant_id);


--
-- Name: invoices_billing_account_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX invoices_billing_account_idx ON oryh.invoices USING btree (billing_account_id);


--
-- Name: invoices_customer_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX invoices_customer_idx ON oryh.invoices USING btree (customer_id);


--
-- Name: invoices_direction_status_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX invoices_direction_status_idx ON oryh.invoices USING btree (tenant_id, direction, status);


--
-- Name: invoices_due_date_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX invoices_due_date_idx ON oryh.invoices USING btree (tenant_id, due_date);


--
-- Name: invoices_employee_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX invoices_employee_idx ON oryh.invoices USING btree (employee_id);


--
-- Name: invoices_payee_employee_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX invoices_payee_employee_idx ON oryh.invoices USING btree (payee_employee_id);


--
-- Name: invoices_payroll_period_uk; Type: INDEX; Schema: oryh; Owner: -
--

CREATE UNIQUE INDEX invoices_payroll_period_uk ON oryh.invoices USING btree (tenant_id, payee_employee_id, period_start) WHERE (((direction)::text = 'payroll'::text) AND (deleted_at IS NULL));


--
-- Name: invoices_purchase_order_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX invoices_purchase_order_idx ON oryh.invoices USING btree (purchase_order_id);


--
-- Name: invoices_sales_order_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX invoices_sales_order_idx ON oryh.invoices USING btree (sales_order_id);


--
-- Name: invoices_tax_invoice_number_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX invoices_tax_invoice_number_idx ON oryh.invoices USING btree (tenant_id, tax_invoice_number);


--
-- Name: invoices_tenant_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX invoices_tenant_idx ON oryh.invoices USING btree (tenant_id);


--
-- Name: invoices_vendor_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX invoices_vendor_idx ON oryh.invoices USING btree (vendor_id);


--
-- Name: object_type_definitions_tenant_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX object_type_definitions_tenant_idx ON oryh.object_type_definitions USING btree (tenant_id, status);


--
-- Name: pay_histories_component_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX pay_histories_component_idx ON oryh.pay_histories USING btree (component);


--
-- Name: pay_histories_employee_from_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX pay_histories_employee_from_idx ON oryh.pay_histories USING btree (tenant_id, employee_id, component, effective_from);


--
-- Name: pay_histories_employee_from_uk; Type: INDEX; Schema: oryh; Owner: -
--

CREATE UNIQUE INDEX pay_histories_employee_from_uk ON oryh.pay_histories USING btree (tenant_id, employee_id, component, effective_from);


--
-- Name: pay_histories_employee_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX pay_histories_employee_idx ON oryh.pay_histories USING btree (employee_id);


--
-- Name: pay_histories_tenant_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX pay_histories_tenant_idx ON oryh.pay_histories USING btree (tenant_id);


--
-- Name: payment_applications_billing_account_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX payment_applications_billing_account_idx ON oryh.payment_applications USING btree (billing_account_id);


--
-- Name: payment_applications_expense_claim_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX payment_applications_expense_claim_idx ON oryh.payment_applications USING btree (expense_claim_id);


--
-- Name: payment_applications_idempotency_uk; Type: INDEX; Schema: oryh; Owner: -
--

CREATE UNIQUE INDEX payment_applications_idempotency_uk ON oryh.payment_applications USING btree (tenant_id, payment_id, idempotency_key, idempotency_seq) WHERE (idempotency_key IS NOT NULL);


--
-- Name: payment_applications_invoice_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX payment_applications_invoice_idx ON oryh.payment_applications USING btree (invoice_id);


--
-- Name: payment_applications_invoice_item_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX payment_applications_invoice_item_idx ON oryh.payment_applications USING btree (invoice_item_id);


--
-- Name: payment_applications_payment_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX payment_applications_payment_idx ON oryh.payment_applications USING btree (payment_id);


--
-- Name: payment_applications_tenant_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX payment_applications_tenant_idx ON oryh.payment_applications USING btree (tenant_id);


--
-- Name: payment_applications_to_payment_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX payment_applications_to_payment_idx ON oryh.payment_applications USING btree (to_payment_id);


--
-- Name: payments_customer_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX payments_customer_idx ON oryh.payments USING btree (customer_id);


--
-- Name: payments_direction_status_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX payments_direction_status_idx ON oryh.payments USING btree (tenant_id, direction, status);


--
-- Name: payments_payee_employee_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX payments_payee_employee_idx ON oryh.payments USING btree (payee_employee_id);


--
-- Name: payments_payment_date_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX payments_payment_date_idx ON oryh.payments USING btree (tenant_id, payment_date);


--
-- Name: payments_reference_no_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX payments_reference_no_idx ON oryh.payments USING btree (tenant_id, reference_no);


--
-- Name: payments_tenant_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX payments_tenant_idx ON oryh.payments USING btree (tenant_id);


--
-- Name: payments_vendor_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX payments_vendor_idx ON oryh.payments USING btree (vendor_id);


--
-- Name: pending_registrations_active_domain_uk; Type: INDEX; Schema: oryh; Owner: -
--

CREATE UNIQUE INDEX pending_registrations_active_domain_uk ON oryh.pending_registrations USING btree (email_domain) WHERE ((status)::text = ANY ((ARRAY['pending_email'::character varying, 'pending_review'::character varying])::text[]));


--
-- Name: pending_registrations_active_email_uk; Type: INDEX; Schema: oryh; Owner: -
--

CREATE UNIQUE INDEX pending_registrations_active_email_uk ON oryh.pending_registrations USING btree (email) WHERE ((status)::text = ANY ((ARRAY['pending_email'::character varying, 'pending_review'::character varying])::text[]));


--
-- Name: pending_registrations_domain_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX pending_registrations_domain_idx ON oryh.pending_registrations USING btree (email_domain);


--
-- Name: pending_registrations_email_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX pending_registrations_email_idx ON oryh.pending_registrations USING btree (email);


--
-- Name: platform_sessions_admin_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX platform_sessions_admin_idx ON oryh.platform_sessions USING btree (platform_admin_id);


--
-- Name: policies_attachment_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX policies_attachment_idx ON oryh.policies USING btree (attachment_id);


--
-- Name: policies_category_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX policies_category_idx ON oryh.policies USING btree (tenant_id, category, status);


--
-- Name: policies_code_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX policies_code_idx ON oryh.policies USING btree (tenant_id, code, version);


--
-- Name: policies_current_version_uk; Type: INDEX; Schema: oryh; Owner: -
--

CREATE UNIQUE INDEX policies_current_version_uk ON oryh.policies USING btree (tenant_id, code) WHERE (((status)::text = 'published'::text) AND (deleted_at IS NULL));


--
-- Name: policies_owner_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX policies_owner_idx ON oryh.policies USING btree (owner_employee_id);


--
-- Name: policies_supersedes_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX policies_supersedes_idx ON oryh.policies USING btree (supersedes_id);


--
-- Name: policies_tenant_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX policies_tenant_idx ON oryh.policies USING btree (tenant_id);


--
-- Name: product_prices_active_product_uq; Type: INDEX; Schema: oryh; Owner: -
--

CREATE UNIQUE INDEX product_prices_active_product_uq ON oryh.product_prices USING btree (tenant_id, product_id, price_type, currency) WHERE ((status = 'active'::text) AND (sku_id IS NULL));


--
-- Name: product_prices_active_sku_uq; Type: INDEX; Schema: oryh; Owner: -
--

CREATE UNIQUE INDEX product_prices_active_sku_uq ON oryh.product_prices USING btree (tenant_id, sku_id, price_type, currency) WHERE ((status = 'active'::text) AND (sku_id IS NOT NULL));


--
-- Name: product_prices_product_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX product_prices_product_idx ON oryh.product_prices USING btree (product_id);


--
-- Name: product_prices_sku_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX product_prices_sku_idx ON oryh.product_prices USING btree (sku_id);


--
-- Name: product_prices_tenant_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX product_prices_tenant_idx ON oryh.product_prices USING btree (tenant_id);


--
-- Name: product_skus_product_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX product_skus_product_idx ON oryh.product_skus USING btree (product_id, status);


--
-- Name: product_skus_tenant_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX product_skus_tenant_idx ON oryh.product_skus USING btree (tenant_id);


--
-- Name: products_tenant_code_uq; Type: INDEX; Schema: oryh; Owner: -
--

CREATE UNIQUE INDEX products_tenant_code_uq ON oryh.products USING btree (tenant_id, product_code) WHERE (product_code IS NOT NULL);


--
-- Name: products_tenant_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX products_tenant_idx ON oryh.products USING btree (tenant_id, status, created_at DESC);


--
-- Name: projects_tenant_project_code_uk; Type: INDEX; Schema: oryh; Owner: -
--

CREATE UNIQUE INDEX projects_tenant_project_code_uk ON oryh.projects USING btree (tenant_id, project_code) WHERE (project_code IS NOT NULL);


--
-- Name: purchase_order_adjustments_po_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX purchase_order_adjustments_po_idx ON oryh.purchase_order_adjustments USING btree (po_id);


--
-- Name: purchase_order_adjustments_tenant_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX purchase_order_adjustments_tenant_idx ON oryh.purchase_order_adjustments USING btree (tenant_id);


--
-- Name: purchase_order_items_po_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX purchase_order_items_po_idx ON oryh.purchase_order_items USING btree (po_id);


--
-- Name: purchase_order_items_request_item_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX purchase_order_items_request_item_idx ON oryh.purchase_order_items USING btree (purchase_request_item_id);


--
-- Name: purchase_order_items_tenant_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX purchase_order_items_tenant_idx ON oryh.purchase_order_items USING btree (tenant_id);


--
-- Name: purchase_orders_employee_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX purchase_orders_employee_idx ON oryh.purchase_orders USING btree (employee_id);


--
-- Name: purchase_orders_tenant_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX purchase_orders_tenant_idx ON oryh.purchase_orders USING btree (tenant_id);


--
-- Name: purchase_orders_vendor_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX purchase_orders_vendor_idx ON oryh.purchase_orders USING btree (vendor_id);


--
-- Name: purchase_request_items_request_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX purchase_request_items_request_idx ON oryh.purchase_request_items USING btree (request_id);


--
-- Name: purchase_request_items_sales_order_item_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX purchase_request_items_sales_order_item_idx ON oryh.purchase_request_items USING btree (sales_order_item_id);


--
-- Name: purchase_requests_employee_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX purchase_requests_employee_idx ON oryh.purchase_requests USING btree (employee_id);


--
-- Name: purchase_requests_tenant_status_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX purchase_requests_tenant_status_idx ON oryh.purchase_requests USING btree (tenant_id, status, created_at DESC);


--
-- Name: resource_bookings_tenant_booked_by_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX resource_bookings_tenant_booked_by_idx ON oryh.resource_bookings USING btree (tenant_id, booked_by_employee_id, start_at DESC);


--
-- Name: resource_bookings_tenant_resource_time_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX resource_bookings_tenant_resource_time_idx ON oryh.resource_bookings USING btree (tenant_id, resource_id, start_at, end_at) WHERE (cancelled_at IS NULL);


--
-- Name: resources_tenant_code_uk; Type: INDEX; Schema: oryh; Owner: -
--

CREATE UNIQUE INDEX resources_tenant_code_uk ON oryh.resources USING btree (tenant_id, code) WHERE (code IS NOT NULL);


--
-- Name: resources_tenant_type_status_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX resources_tenant_type_status_idx ON oryh.resources USING btree (tenant_id, resource_type, status, created_at DESC);


--
-- Name: roles_tenant_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX roles_tenant_idx ON oryh.roles USING btree (tenant_id);


--
-- Name: sales_order_adjustments_item_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX sales_order_adjustments_item_idx ON oryh.sales_order_adjustments USING btree (order_item_id);


--
-- Name: sales_order_adjustments_parent_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX sales_order_adjustments_parent_idx ON oryh.sales_order_adjustments USING btree (order_id);


--
-- Name: sales_order_adjustments_tenant_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX sales_order_adjustments_tenant_idx ON oryh.sales_order_adjustments USING btree (tenant_id);


--
-- Name: sales_order_items_order_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX sales_order_items_order_idx ON oryh.sales_order_items USING btree (order_id);


--
-- Name: sales_orders_customer_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX sales_orders_customer_idx ON oryh.sales_orders USING btree (customer_id);


--
-- Name: sales_orders_employee_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX sales_orders_employee_idx ON oryh.sales_orders USING btree (employee_id);


--
-- Name: sales_orders_quotation_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX sales_orders_quotation_idx ON oryh.sales_orders USING btree (quotation_id);


--
-- Name: sales_orders_tenant_status_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX sales_orders_tenant_status_idx ON oryh.sales_orders USING btree (tenant_id, status, created_at DESC);


--
-- Name: sales_quotation_adjustments_item_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX sales_quotation_adjustments_item_idx ON oryh.sales_quotation_adjustments USING btree (quotation_item_id);


--
-- Name: sales_quotation_adjustments_parent_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX sales_quotation_adjustments_parent_idx ON oryh.sales_quotation_adjustments USING btree (quotation_id);


--
-- Name: sales_quotation_adjustments_tenant_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX sales_quotation_adjustments_tenant_idx ON oryh.sales_quotation_adjustments USING btree (tenant_id);


--
-- Name: sales_quotation_items_quotation_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX sales_quotation_items_quotation_idx ON oryh.sales_quotation_items USING btree (quotation_id);


--
-- Name: sales_quotations_customer_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX sales_quotations_customer_idx ON oryh.sales_quotations USING btree (customer_id);


--
-- Name: sales_quotations_employee_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX sales_quotations_employee_idx ON oryh.sales_quotations USING btree (employee_id);


--
-- Name: sales_quotations_tenant_status_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX sales_quotations_tenant_status_idx ON oryh.sales_quotations USING btree (tenant_id, status, created_at DESC);


--
-- Name: supplier_products_product_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX supplier_products_product_idx ON oryh.supplier_products USING btree (product_id);


--
-- Name: supplier_products_tenant_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX supplier_products_tenant_idx ON oryh.supplier_products USING btree (tenant_id);


--
-- Name: supplier_products_vendor_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX supplier_products_vendor_idx ON oryh.supplier_products USING btree (vendor_id);


--
-- Name: tenant_skill_assignments_skill_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX tenant_skill_assignments_skill_idx ON oryh.tenant_skill_assignments USING btree (skill_id);


--
-- Name: tenant_skill_assignments_subject_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX tenant_skill_assignments_subject_idx ON oryh.tenant_skill_assignments USING btree (tenant_id, subject_type, subject_id);


--
-- Name: tenant_skill_assignments_tenant_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX tenant_skill_assignments_tenant_idx ON oryh.tenant_skill_assignments USING btree (tenant_id);


--
-- Name: tenant_skills_tenant_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX tenant_skills_tenant_idx ON oryh.tenant_skills USING btree (tenant_id, status);


--
-- Name: tenants_slug_key; Type: INDEX; Schema: oryh; Owner: -
--

CREATE UNIQUE INDEX tenants_slug_key ON oryh.tenants USING btree (slug);


--
-- Name: timesheet_entries_tenant_employee_date_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX timesheet_entries_tenant_employee_date_idx ON oryh.timesheet_entries USING btree (tenant_id, employee_id, work_date) WHERE (deleted_at IS NULL);


--
-- Name: timesheet_entries_tenant_header_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX timesheet_entries_tenant_header_idx ON oryh.timesheet_entries USING btree (tenant_id, header_id) WHERE (deleted_at IS NULL);


--
-- Name: timesheet_headers_tenant_active_period_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX timesheet_headers_tenant_active_period_idx ON oryh.timesheet_headers USING btree (tenant_id, employee_id, period_start DESC) WHERE (deleted_at IS NULL);


--
-- Name: timesheet_headers_tenant_employee_period_uk; Type: INDEX; Schema: oryh; Owner: -
--

CREATE UNIQUE INDEX timesheet_headers_tenant_employee_period_uk ON oryh.timesheet_headers USING btree (tenant_id, employee_id, period_start, period_end);


--
-- Name: todos_open_entity_assignee_uk; Type: INDEX; Schema: oryh; Owner: -
--

CREATE UNIQUE INDEX todos_open_entity_assignee_uk ON oryh.todos USING btree (tenant_id, employee_id, entity_type, entity_id) WHERE (status = 'open'::text);


--
-- Name: todos_tenant_assignee_status_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX todos_tenant_assignee_status_idx ON oryh.todos USING btree (tenant_id, employee_id, status, created_at DESC);


--
-- Name: type_options_family_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX type_options_family_idx ON oryh.type_options USING btree (family);


--
-- Name: type_options_tenant_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX type_options_tenant_idx ON oryh.type_options USING btree (tenant_id);


--
-- Name: user_sessions_user_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX user_sessions_user_idx ON oryh.user_sessions USING btree (user_id);


--
-- Name: users_tenant_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX users_tenant_idx ON oryh.users USING btree (tenant_id);


--
-- Name: vendors_tenant_code_uq; Type: INDEX; Schema: oryh; Owner: -
--

CREATE UNIQUE INDEX vendors_tenant_code_uq ON oryh.vendors USING btree (tenant_id, vendor_code) WHERE (vendor_code IS NOT NULL);


--
-- Name: vendors_tenant_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX vendors_tenant_idx ON oryh.vendors USING btree (tenant_id, status, created_at DESC);


--
-- Name: vendors_tenant_tax_id_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX vendors_tenant_tax_id_idx ON oryh.vendors USING btree (tenant_id, tax_id) WHERE (tax_id IS NOT NULL);


--
-- Name: workflow_definitions_tenant_idx; Type: INDEX; Schema: oryh; Owner: -
--

CREATE INDEX workflow_definitions_tenant_idx ON oryh.workflow_definitions USING btree (tenant_id, entity_kind, object_type, name, status);


--
-- Name: api_keys api_keys_tenant_id_fkey; Type: FK CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.api_keys
    ADD CONSTRAINT api_keys_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES oryh.tenants(id);


--
-- Name: api_keys api_keys_user_id_fkey; Type: FK CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.api_keys
    ADD CONSTRAINT api_keys_user_id_fkey FOREIGN KEY (user_id) REFERENCES oryh.users(id);


--
-- Name: billing_account_entries billing_account_entries_billing_account_id_fkey; Type: FK CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.billing_account_entries
    ADD CONSTRAINT billing_account_entries_billing_account_id_fkey FOREIGN KEY (billing_account_id) REFERENCES oryh.billing_accounts(id);


--
-- Name: billing_accounts billing_accounts_customer_id_fkey; Type: FK CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.billing_accounts
    ADD CONSTRAINT billing_accounts_customer_id_fkey FOREIGN KEY (customer_id) REFERENCES oryh.customers(id);


--
-- Name: billing_accounts billing_accounts_employee_id_fkey; Type: FK CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.billing_accounts
    ADD CONSTRAINT billing_accounts_employee_id_fkey FOREIGN KEY (employee_id) REFERENCES oryh.employees(id);


--
-- Name: billing_accounts billing_accounts_vendor_id_fkey; Type: FK CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.billing_accounts
    ADD CONSTRAINT billing_accounts_vendor_id_fkey FOREIGN KEY (vendor_id) REFERENCES oryh.vendors(id);


--
-- Name: business_object_links business_object_links_source_object_id_fkey; Type: FK CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.business_object_links
    ADD CONSTRAINT business_object_links_source_object_id_fkey FOREIGN KEY (source_object_id) REFERENCES oryh.business_objects(id);


--
-- Name: business_object_links business_object_links_target_object_id_fkey; Type: FK CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.business_object_links
    ADD CONSTRAINT business_object_links_target_object_id_fkey FOREIGN KEY (target_object_id) REFERENCES oryh.business_objects(id);


--
-- Name: enterprise_pilot_applications enterprise_pilot_applications_reviewed_by_fkey; Type: FK CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.enterprise_pilot_applications
    ADD CONSTRAINT enterprise_pilot_applications_reviewed_by_fkey FOREIGN KEY (reviewed_by) REFERENCES oryh.platform_admins(id);


--
-- Name: expense_claims expense_claims_employee_id_fkey; Type: FK CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.expense_claims
    ADD CONSTRAINT expense_claims_employee_id_fkey FOREIGN KEY (employee_id) REFERENCES oryh.employees(id);


--
-- Name: expense_items expense_items_attachment_id_fkey; Type: FK CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.expense_items
    ADD CONSTRAINT expense_items_attachment_id_fkey FOREIGN KEY (attachment_id) REFERENCES oryh.attachments(id);


--
-- Name: expense_items expense_items_claim_id_fkey; Type: FK CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.expense_items
    ADD CONSTRAINT expense_items_claim_id_fkey FOREIGN KEY (claim_id) REFERENCES oryh.expense_claims(id);


--
-- Name: expense_items expense_items_employee_id_fkey; Type: FK CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.expense_items
    ADD CONSTRAINT expense_items_employee_id_fkey FOREIGN KEY (employee_id) REFERENCES oryh.employees(id);


--
-- Name: expense_items expense_items_project_id_fkey; Type: FK CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.expense_items
    ADD CONSTRAINT expense_items_project_id_fkey FOREIGN KEY (project_id) REFERENCES oryh.projects(id);


--
-- Name: expense_items expense_items_vendor_id_fkey; Type: FK CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.expense_items
    ADD CONSTRAINT expense_items_vendor_id_fkey FOREIGN KEY (vendor_id) REFERENCES oryh.vendors(id);


--
-- Name: flow_runs flow_runs_subscription_id_fkey; Type: FK CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.flow_runs
    ADD CONSTRAINT flow_runs_subscription_id_fkey FOREIGN KEY (subscription_id) REFERENCES oryh.flow_subscriptions(id);


--
-- Name: flow_subscriptions flow_subscriptions_api_key_id_fkey; Type: FK CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.flow_subscriptions
    ADD CONSTRAINT flow_subscriptions_api_key_id_fkey FOREIGN KEY (api_key_id) REFERENCES oryh.api_keys(id);


--
-- Name: inventory_item_details inventory_item_details_inventory_item_id_fkey; Type: FK CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.inventory_item_details
    ADD CONSTRAINT inventory_item_details_inventory_item_id_fkey FOREIGN KEY (inventory_item_id) REFERENCES oryh.inventory_items(id);


--
-- Name: inventory_items inventory_items_product_id_fkey; Type: FK CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.inventory_items
    ADD CONSTRAINT inventory_items_product_id_fkey FOREIGN KEY (product_id) REFERENCES oryh.products(id);


--
-- Name: inventory_items inventory_items_sku_id_fkey; Type: FK CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.inventory_items
    ADD CONSTRAINT inventory_items_sku_id_fkey FOREIGN KEY (sku_id) REFERENCES oryh.product_skus(id);


--
-- Name: invoice_items invoice_items_invoice_id_fkey; Type: FK CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.invoice_items
    ADD CONSTRAINT invoice_items_invoice_id_fkey FOREIGN KEY (invoice_id) REFERENCES oryh.invoices(id);


--
-- Name: invoice_items invoice_items_pay_history_id_fkey; Type: FK CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.invoice_items
    ADD CONSTRAINT invoice_items_pay_history_id_fkey FOREIGN KEY (pay_history_id) REFERENCES oryh.pay_histories(id);


--
-- Name: invoice_items invoice_items_product_id_fkey; Type: FK CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.invoice_items
    ADD CONSTRAINT invoice_items_product_id_fkey FOREIGN KEY (product_id) REFERENCES oryh.products(id);


--
-- Name: invoice_items invoice_items_purchase_order_item_id_fkey; Type: FK CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.invoice_items
    ADD CONSTRAINT invoice_items_purchase_order_item_id_fkey FOREIGN KEY (purchase_order_item_id) REFERENCES oryh.purchase_order_items(id);


--
-- Name: invoice_items invoice_items_sales_order_item_id_fkey; Type: FK CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.invoice_items
    ADD CONSTRAINT invoice_items_sales_order_item_id_fkey FOREIGN KEY (sales_order_item_id) REFERENCES oryh.sales_order_items(id);


--
-- Name: invoice_items invoice_items_sku_id_fkey; Type: FK CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.invoice_items
    ADD CONSTRAINT invoice_items_sku_id_fkey FOREIGN KEY (sku_id) REFERENCES oryh.product_skus(id);


--
-- Name: invoices invoices_attachment_id_fkey; Type: FK CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.invoices
    ADD CONSTRAINT invoices_attachment_id_fkey FOREIGN KEY (attachment_id) REFERENCES oryh.attachments(id);


--
-- Name: invoices invoices_billing_account_id_fkey; Type: FK CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.invoices
    ADD CONSTRAINT invoices_billing_account_id_fkey FOREIGN KEY (billing_account_id) REFERENCES oryh.billing_accounts(id);


--
-- Name: invoices invoices_customer_id_fkey; Type: FK CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.invoices
    ADD CONSTRAINT invoices_customer_id_fkey FOREIGN KEY (customer_id) REFERENCES oryh.customers(id);


--
-- Name: invoices invoices_employee_id_fkey; Type: FK CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.invoices
    ADD CONSTRAINT invoices_employee_id_fkey FOREIGN KEY (employee_id) REFERENCES oryh.employees(id);


--
-- Name: invoices invoices_payee_employee_id_fkey; Type: FK CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.invoices
    ADD CONSTRAINT invoices_payee_employee_id_fkey FOREIGN KEY (payee_employee_id) REFERENCES oryh.employees(id);


--
-- Name: invoices invoices_project_id_fkey; Type: FK CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.invoices
    ADD CONSTRAINT invoices_project_id_fkey FOREIGN KEY (project_id) REFERENCES oryh.projects(id);


--
-- Name: invoices invoices_purchase_order_id_fkey; Type: FK CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.invoices
    ADD CONSTRAINT invoices_purchase_order_id_fkey FOREIGN KEY (purchase_order_id) REFERENCES oryh.purchase_orders(id);


--
-- Name: invoices invoices_sales_order_id_fkey; Type: FK CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.invoices
    ADD CONSTRAINT invoices_sales_order_id_fkey FOREIGN KEY (sales_order_id) REFERENCES oryh.sales_orders(id);


--
-- Name: invoices invoices_vendor_id_fkey; Type: FK CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.invoices
    ADD CONSTRAINT invoices_vendor_id_fkey FOREIGN KEY (vendor_id) REFERENCES oryh.vendors(id);


--
-- Name: pay_histories pay_histories_employee_id_fkey; Type: FK CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.pay_histories
    ADD CONSTRAINT pay_histories_employee_id_fkey FOREIGN KEY (employee_id) REFERENCES oryh.employees(id);


--
-- Name: payment_applications payment_applications_billing_account_id_fkey; Type: FK CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.payment_applications
    ADD CONSTRAINT payment_applications_billing_account_id_fkey FOREIGN KEY (billing_account_id) REFERENCES oryh.billing_accounts(id);


--
-- Name: payment_applications payment_applications_expense_claim_id_fkey; Type: FK CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.payment_applications
    ADD CONSTRAINT payment_applications_expense_claim_id_fkey FOREIGN KEY (expense_claim_id) REFERENCES oryh.expense_claims(id);


--
-- Name: payment_applications payment_applications_invoice_id_fkey; Type: FK CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.payment_applications
    ADD CONSTRAINT payment_applications_invoice_id_fkey FOREIGN KEY (invoice_id) REFERENCES oryh.invoices(id);


--
-- Name: payment_applications payment_applications_invoice_item_id_fkey; Type: FK CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.payment_applications
    ADD CONSTRAINT payment_applications_invoice_item_id_fkey FOREIGN KEY (invoice_item_id) REFERENCES oryh.invoice_items(id);


--
-- Name: payment_applications payment_applications_payment_id_fkey; Type: FK CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.payment_applications
    ADD CONSTRAINT payment_applications_payment_id_fkey FOREIGN KEY (payment_id) REFERENCES oryh.payments(id);


--
-- Name: payment_applications payment_applications_to_payment_id_fkey; Type: FK CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.payment_applications
    ADD CONSTRAINT payment_applications_to_payment_id_fkey FOREIGN KEY (to_payment_id) REFERENCES oryh.payments(id);


--
-- Name: payments payments_attachment_id_fkey; Type: FK CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.payments
    ADD CONSTRAINT payments_attachment_id_fkey FOREIGN KEY (attachment_id) REFERENCES oryh.attachments(id);


--
-- Name: payments payments_customer_id_fkey; Type: FK CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.payments
    ADD CONSTRAINT payments_customer_id_fkey FOREIGN KEY (customer_id) REFERENCES oryh.customers(id);


--
-- Name: payments payments_employee_id_fkey; Type: FK CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.payments
    ADD CONSTRAINT payments_employee_id_fkey FOREIGN KEY (employee_id) REFERENCES oryh.employees(id);


--
-- Name: payments payments_payee_employee_id_fkey; Type: FK CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.payments
    ADD CONSTRAINT payments_payee_employee_id_fkey FOREIGN KEY (payee_employee_id) REFERENCES oryh.employees(id);


--
-- Name: payments payments_vendor_id_fkey; Type: FK CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.payments
    ADD CONSTRAINT payments_vendor_id_fkey FOREIGN KEY (vendor_id) REFERENCES oryh.vendors(id);


--
-- Name: pending_registrations pending_registrations_reviewer_fk; Type: FK CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.pending_registrations
    ADD CONSTRAINT pending_registrations_reviewer_fk FOREIGN KEY (reviewed_by) REFERENCES oryh.platform_admins(id);


--
-- Name: pending_registrations pending_registrations_tenant_fk; Type: FK CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.pending_registrations
    ADD CONSTRAINT pending_registrations_tenant_fk FOREIGN KEY (tenant_id) REFERENCES oryh.tenants(id);


--
-- Name: platform_sessions platform_sessions_platform_admin_id_fkey; Type: FK CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.platform_sessions
    ADD CONSTRAINT platform_sessions_platform_admin_id_fkey FOREIGN KEY (platform_admin_id) REFERENCES oryh.platform_admins(id);


--
-- Name: policies policies_attachment_id_fkey; Type: FK CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.policies
    ADD CONSTRAINT policies_attachment_id_fkey FOREIGN KEY (attachment_id) REFERENCES oryh.attachments(id);


--
-- Name: policies policies_owner_employee_id_fkey; Type: FK CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.policies
    ADD CONSTRAINT policies_owner_employee_id_fkey FOREIGN KEY (owner_employee_id) REFERENCES oryh.employees(id);


--
-- Name: policies policies_supersedes_id_fkey; Type: FK CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.policies
    ADD CONSTRAINT policies_supersedes_id_fkey FOREIGN KEY (supersedes_id) REFERENCES oryh.policies(id);


--
-- Name: product_prices product_prices_product_id_fkey; Type: FK CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.product_prices
    ADD CONSTRAINT product_prices_product_id_fkey FOREIGN KEY (product_id) REFERENCES oryh.products(id);


--
-- Name: product_prices product_prices_sku_id_fkey; Type: FK CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.product_prices
    ADD CONSTRAINT product_prices_sku_id_fkey FOREIGN KEY (sku_id) REFERENCES oryh.product_skus(id);


--
-- Name: product_skus product_skus_product_id_fkey; Type: FK CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.product_skus
    ADD CONSTRAINT product_skus_product_id_fkey FOREIGN KEY (product_id) REFERENCES oryh.products(id);


--
-- Name: purchase_order_adjustments purchase_order_adjustments_po_id_fkey; Type: FK CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.purchase_order_adjustments
    ADD CONSTRAINT purchase_order_adjustments_po_id_fkey FOREIGN KEY (po_id) REFERENCES oryh.purchase_orders(id);


--
-- Name: purchase_order_adjustments purchase_order_adjustments_po_item_id_fkey; Type: FK CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.purchase_order_adjustments
    ADD CONSTRAINT purchase_order_adjustments_po_item_id_fkey FOREIGN KEY (po_item_id) REFERENCES oryh.purchase_order_items(id);


--
-- Name: purchase_order_items purchase_order_items_attachment_id_fkey; Type: FK CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.purchase_order_items
    ADD CONSTRAINT purchase_order_items_attachment_id_fkey FOREIGN KEY (attachment_id) REFERENCES oryh.attachments(id);


--
-- Name: purchase_order_items purchase_order_items_po_id_fkey; Type: FK CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.purchase_order_items
    ADD CONSTRAINT purchase_order_items_po_id_fkey FOREIGN KEY (po_id) REFERENCES oryh.purchase_orders(id);


--
-- Name: purchase_order_items purchase_order_items_product_id_fkey; Type: FK CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.purchase_order_items
    ADD CONSTRAINT purchase_order_items_product_id_fkey FOREIGN KEY (product_id) REFERENCES oryh.products(id);


--
-- Name: purchase_order_items purchase_order_items_purchase_request_item_id_fkey; Type: FK CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.purchase_order_items
    ADD CONSTRAINT purchase_order_items_purchase_request_item_id_fkey FOREIGN KEY (purchase_request_item_id) REFERENCES oryh.purchase_request_items(id);


--
-- Name: purchase_order_items purchase_order_items_sku_id_fkey; Type: FK CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.purchase_order_items
    ADD CONSTRAINT purchase_order_items_sku_id_fkey FOREIGN KEY (sku_id) REFERENCES oryh.product_skus(id);


--
-- Name: purchase_orders purchase_orders_employee_id_fkey; Type: FK CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.purchase_orders
    ADD CONSTRAINT purchase_orders_employee_id_fkey FOREIGN KEY (employee_id) REFERENCES oryh.employees(id);


--
-- Name: purchase_orders purchase_orders_vendor_id_fkey; Type: FK CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.purchase_orders
    ADD CONSTRAINT purchase_orders_vendor_id_fkey FOREIGN KEY (vendor_id) REFERENCES oryh.vendors(id);


--
-- Name: purchase_request_items purchase_request_items_attachment_id_fkey; Type: FK CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.purchase_request_items
    ADD CONSTRAINT purchase_request_items_attachment_id_fkey FOREIGN KEY (attachment_id) REFERENCES oryh.attachments(id);


--
-- Name: purchase_request_items purchase_request_items_product_id_fkey; Type: FK CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.purchase_request_items
    ADD CONSTRAINT purchase_request_items_product_id_fkey FOREIGN KEY (product_id) REFERENCES oryh.products(id);


--
-- Name: purchase_request_items purchase_request_items_request_id_fkey; Type: FK CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.purchase_request_items
    ADD CONSTRAINT purchase_request_items_request_id_fkey FOREIGN KEY (request_id) REFERENCES oryh.purchase_requests(id);


--
-- Name: purchase_request_items purchase_request_items_sales_order_item_id_fkey; Type: FK CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.purchase_request_items
    ADD CONSTRAINT purchase_request_items_sales_order_item_id_fkey FOREIGN KEY (sales_order_item_id) REFERENCES oryh.sales_order_items(id);


--
-- Name: purchase_request_items purchase_request_items_sku_id_fkey; Type: FK CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.purchase_request_items
    ADD CONSTRAINT purchase_request_items_sku_id_fkey FOREIGN KEY (sku_id) REFERENCES oryh.product_skus(id);


--
-- Name: purchase_requests purchase_requests_employee_id_fkey; Type: FK CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.purchase_requests
    ADD CONSTRAINT purchase_requests_employee_id_fkey FOREIGN KEY (employee_id) REFERENCES oryh.employees(id);


--
-- Name: purchase_requests purchase_requests_vendor_id_fkey; Type: FK CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.purchase_requests
    ADD CONSTRAINT purchase_requests_vendor_id_fkey FOREIGN KEY (vendor_id) REFERENCES oryh.vendors(id);


--
-- Name: resource_bookings resource_bookings_booked_by_employee_id_fkey; Type: FK CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.resource_bookings
    ADD CONSTRAINT resource_bookings_booked_by_employee_id_fkey FOREIGN KEY (booked_by_employee_id) REFERENCES oryh.employees(id);


--
-- Name: resource_bookings resource_bookings_resource_id_fkey; Type: FK CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.resource_bookings
    ADD CONSTRAINT resource_bookings_resource_id_fkey FOREIGN KEY (resource_id) REFERENCES oryh.resources(id);


--
-- Name: sales_order_adjustments sales_order_adjustments_order_id_fkey; Type: FK CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.sales_order_adjustments
    ADD CONSTRAINT sales_order_adjustments_order_id_fkey FOREIGN KEY (order_id) REFERENCES oryh.sales_orders(id);


--
-- Name: sales_order_adjustments sales_order_adjustments_order_item_id_fkey; Type: FK CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.sales_order_adjustments
    ADD CONSTRAINT sales_order_adjustments_order_item_id_fkey FOREIGN KEY (order_item_id) REFERENCES oryh.sales_order_items(id);


--
-- Name: sales_order_items sales_order_items_attachment_id_fkey; Type: FK CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.sales_order_items
    ADD CONSTRAINT sales_order_items_attachment_id_fkey FOREIGN KEY (attachment_id) REFERENCES oryh.attachments(id);


--
-- Name: sales_order_items sales_order_items_order_id_fkey; Type: FK CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.sales_order_items
    ADD CONSTRAINT sales_order_items_order_id_fkey FOREIGN KEY (order_id) REFERENCES oryh.sales_orders(id);


--
-- Name: sales_order_items sales_order_items_product_id_fkey; Type: FK CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.sales_order_items
    ADD CONSTRAINT sales_order_items_product_id_fkey FOREIGN KEY (product_id) REFERENCES oryh.products(id);


--
-- Name: sales_order_items sales_order_items_sku_id_fkey; Type: FK CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.sales_order_items
    ADD CONSTRAINT sales_order_items_sku_id_fkey FOREIGN KEY (sku_id) REFERENCES oryh.product_skus(id);


--
-- Name: sales_orders sales_orders_customer_id_fkey; Type: FK CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.sales_orders
    ADD CONSTRAINT sales_orders_customer_id_fkey FOREIGN KEY (customer_id) REFERENCES oryh.customers(id);


--
-- Name: sales_orders sales_orders_employee_id_fkey; Type: FK CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.sales_orders
    ADD CONSTRAINT sales_orders_employee_id_fkey FOREIGN KEY (employee_id) REFERENCES oryh.employees(id);


--
-- Name: sales_orders sales_orders_project_id_fkey; Type: FK CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.sales_orders
    ADD CONSTRAINT sales_orders_project_id_fkey FOREIGN KEY (project_id) REFERENCES oryh.projects(id);


--
-- Name: sales_orders sales_orders_quotation_id_fkey; Type: FK CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.sales_orders
    ADD CONSTRAINT sales_orders_quotation_id_fkey FOREIGN KEY (quotation_id) REFERENCES oryh.sales_quotations(id);


--
-- Name: sales_quotation_adjustments sales_quotation_adjustments_quotation_id_fkey; Type: FK CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.sales_quotation_adjustments
    ADD CONSTRAINT sales_quotation_adjustments_quotation_id_fkey FOREIGN KEY (quotation_id) REFERENCES oryh.sales_quotations(id);


--
-- Name: sales_quotation_adjustments sales_quotation_adjustments_quotation_item_id_fkey; Type: FK CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.sales_quotation_adjustments
    ADD CONSTRAINT sales_quotation_adjustments_quotation_item_id_fkey FOREIGN KEY (quotation_item_id) REFERENCES oryh.sales_quotation_items(id);


--
-- Name: sales_quotation_items sales_quotation_items_attachment_id_fkey; Type: FK CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.sales_quotation_items
    ADD CONSTRAINT sales_quotation_items_attachment_id_fkey FOREIGN KEY (attachment_id) REFERENCES oryh.attachments(id);


--
-- Name: sales_quotation_items sales_quotation_items_product_id_fkey; Type: FK CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.sales_quotation_items
    ADD CONSTRAINT sales_quotation_items_product_id_fkey FOREIGN KEY (product_id) REFERENCES oryh.products(id);


--
-- Name: sales_quotation_items sales_quotation_items_quotation_id_fkey; Type: FK CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.sales_quotation_items
    ADD CONSTRAINT sales_quotation_items_quotation_id_fkey FOREIGN KEY (quotation_id) REFERENCES oryh.sales_quotations(id);


--
-- Name: sales_quotation_items sales_quotation_items_sku_id_fkey; Type: FK CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.sales_quotation_items
    ADD CONSTRAINT sales_quotation_items_sku_id_fkey FOREIGN KEY (sku_id) REFERENCES oryh.product_skus(id);


--
-- Name: sales_quotations sales_quotations_customer_id_fkey; Type: FK CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.sales_quotations
    ADD CONSTRAINT sales_quotations_customer_id_fkey FOREIGN KEY (customer_id) REFERENCES oryh.customers(id);


--
-- Name: sales_quotations sales_quotations_employee_id_fkey; Type: FK CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.sales_quotations
    ADD CONSTRAINT sales_quotations_employee_id_fkey FOREIGN KEY (employee_id) REFERENCES oryh.employees(id);


--
-- Name: sales_quotations sales_quotations_project_id_fkey; Type: FK CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.sales_quotations
    ADD CONSTRAINT sales_quotations_project_id_fkey FOREIGN KEY (project_id) REFERENCES oryh.projects(id);


--
-- Name: sales_quotations sales_quotations_revision_of_id_fkey; Type: FK CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.sales_quotations
    ADD CONSTRAINT sales_quotations_revision_of_id_fkey FOREIGN KEY (revision_of_id) REFERENCES oryh.sales_quotations(id);


--
-- Name: supplier_products supplier_products_product_id_fkey; Type: FK CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.supplier_products
    ADD CONSTRAINT supplier_products_product_id_fkey FOREIGN KEY (product_id) REFERENCES oryh.products(id);


--
-- Name: supplier_products supplier_products_vendor_id_fkey; Type: FK CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.supplier_products
    ADD CONSTRAINT supplier_products_vendor_id_fkey FOREIGN KEY (vendor_id) REFERENCES oryh.vendors(id);


--
-- Name: tenant_skill_assignments tenant_skill_assignments_skill_id_fkey; Type: FK CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.tenant_skill_assignments
    ADD CONSTRAINT tenant_skill_assignments_skill_id_fkey FOREIGN KEY (skill_id) REFERENCES oryh.tenant_skills(id) ON DELETE CASCADE;


--
-- Name: timesheet_entries timesheet_entries_employee_id_fkey; Type: FK CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.timesheet_entries
    ADD CONSTRAINT timesheet_entries_employee_id_fkey FOREIGN KEY (employee_id) REFERENCES oryh.employees(id);


--
-- Name: timesheet_entries timesheet_entries_header_id_fkey; Type: FK CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.timesheet_entries
    ADD CONSTRAINT timesheet_entries_header_id_fkey FOREIGN KEY (header_id) REFERENCES oryh.timesheet_headers(id);


--
-- Name: timesheet_entries timesheet_entries_project_id_fkey; Type: FK CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.timesheet_entries
    ADD CONSTRAINT timesheet_entries_project_id_fkey FOREIGN KEY (project_id) REFERENCES oryh.projects(id);


--
-- Name: timesheet_headers timesheet_headers_employee_id_fkey; Type: FK CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.timesheet_headers
    ADD CONSTRAINT timesheet_headers_employee_id_fkey FOREIGN KEY (employee_id) REFERENCES oryh.employees(id);


--
-- Name: todos todos_employee_id_fkey; Type: FK CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.todos
    ADD CONSTRAINT todos_employee_id_fkey FOREIGN KEY (employee_id) REFERENCES oryh.employees(id);


--
-- Name: user_sessions user_sessions_user_id_fkey; Type: FK CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.user_sessions
    ADD CONSTRAINT user_sessions_user_id_fkey FOREIGN KEY (user_id) REFERENCES oryh.users(id);


--
-- Name: users users_employee_id_fkey; Type: FK CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.users
    ADD CONSTRAINT users_employee_id_fkey FOREIGN KEY (employee_id) REFERENCES oryh.employees(id);


--
-- Name: users users_tenant_id_fkey; Type: FK CONSTRAINT; Schema: oryh; Owner: -
--

ALTER TABLE ONLY oryh.users
    ADD CONSTRAINT users_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES oryh.tenants(id);


--
-- Name: api_keys; Type: ROW SECURITY; Schema: oryh; Owner: -
--

ALTER TABLE oryh.api_keys ENABLE ROW LEVEL SECURITY;

--
-- Name: approval_records; Type: ROW SECURITY; Schema: oryh; Owner: -
--

ALTER TABLE oryh.approval_records ENABLE ROW LEVEL SECURITY;

--
-- Name: attachments; Type: ROW SECURITY; Schema: oryh; Owner: -
--

ALTER TABLE oryh.attachments ENABLE ROW LEVEL SECURITY;

--
-- Name: audit_logs; Type: ROW SECURITY; Schema: oryh; Owner: -
--

ALTER TABLE oryh.audit_logs ENABLE ROW LEVEL SECURITY;

--
-- Name: api_keys auth_lookup; Type: POLICY; Schema: oryh; Owner: -
--

CREATE POLICY auth_lookup ON oryh.api_keys FOR SELECT USING (true);


--
-- Name: users auth_lookup; Type: POLICY; Schema: oryh; Owner: -
--

CREATE POLICY auth_lookup ON oryh.users FOR SELECT USING (true);


--
-- Name: billing_account_entries; Type: ROW SECURITY; Schema: oryh; Owner: -
--

ALTER TABLE oryh.billing_account_entries ENABLE ROW LEVEL SECURITY;

--
-- Name: billing_accounts; Type: ROW SECURITY; Schema: oryh; Owner: -
--

ALTER TABLE oryh.billing_accounts ENABLE ROW LEVEL SECURITY;

--
-- Name: business_object_links; Type: ROW SECURITY; Schema: oryh; Owner: -
--

ALTER TABLE oryh.business_object_links ENABLE ROW LEVEL SECURITY;

--
-- Name: business_objects; Type: ROW SECURITY; Schema: oryh; Owner: -
--

ALTER TABLE oryh.business_objects ENABLE ROW LEVEL SECURITY;

--
-- Name: capabilities; Type: ROW SECURITY; Schema: oryh; Owner: -
--

ALTER TABLE oryh.capabilities ENABLE ROW LEVEL SECURITY;

--
-- Name: customers; Type: ROW SECURITY; Schema: oryh; Owner: -
--

ALTER TABLE oryh.customers ENABLE ROW LEVEL SECURITY;

--
-- Name: employees; Type: ROW SECURITY; Schema: oryh; Owner: -
--

ALTER TABLE oryh.employees ENABLE ROW LEVEL SECURITY;

--
-- Name: expense_claims; Type: ROW SECURITY; Schema: oryh; Owner: -
--

ALTER TABLE oryh.expense_claims ENABLE ROW LEVEL SECURITY;

--
-- Name: expense_items; Type: ROW SECURITY; Schema: oryh; Owner: -
--

ALTER TABLE oryh.expense_items ENABLE ROW LEVEL SECURITY;

--
-- Name: flow_runs; Type: ROW SECURITY; Schema: oryh; Owner: -
--

ALTER TABLE oryh.flow_runs ENABLE ROW LEVEL SECURITY;

--
-- Name: flow_subscriptions; Type: ROW SECURITY; Schema: oryh; Owner: -
--

ALTER TABLE oryh.flow_subscriptions ENABLE ROW LEVEL SECURITY;

--
-- Name: inventory_item_details; Type: ROW SECURITY; Schema: oryh; Owner: -
--

ALTER TABLE oryh.inventory_item_details ENABLE ROW LEVEL SECURITY;

--
-- Name: inventory_items; Type: ROW SECURITY; Schema: oryh; Owner: -
--

ALTER TABLE oryh.inventory_items ENABLE ROW LEVEL SECURITY;

--
-- Name: invoice_items; Type: ROW SECURITY; Schema: oryh; Owner: -
--

ALTER TABLE oryh.invoice_items ENABLE ROW LEVEL SECURITY;

--
-- Name: invoices; Type: ROW SECURITY; Schema: oryh; Owner: -
--

ALTER TABLE oryh.invoices ENABLE ROW LEVEL SECURITY;

--
-- Name: object_type_definitions; Type: ROW SECURITY; Schema: oryh; Owner: -
--

ALTER TABLE oryh.object_type_definitions ENABLE ROW LEVEL SECURITY;

--
-- Name: pay_histories; Type: ROW SECURITY; Schema: oryh; Owner: -
--

ALTER TABLE oryh.pay_histories ENABLE ROW LEVEL SECURITY;

--
-- Name: payment_applications; Type: ROW SECURITY; Schema: oryh; Owner: -
--

ALTER TABLE oryh.payment_applications ENABLE ROW LEVEL SECURITY;

--
-- Name: payments; Type: ROW SECURITY; Schema: oryh; Owner: -
--

ALTER TABLE oryh.payments ENABLE ROW LEVEL SECURITY;

--
-- Name: flow_runs platform_update; Type: POLICY; Schema: oryh; Owner: -
--

CREATE POLICY platform_update ON oryh.flow_runs FOR UPDATE USING ((((tenant_id)::text = current_setting('app.tenant_id'::text, true)) OR (current_setting('app.is_platform_admin'::text, true) = 'on'::text))) WITH CHECK ((((tenant_id)::text = current_setting('app.tenant_id'::text, true)) OR (current_setting('app.is_platform_admin'::text, true) = 'on'::text)));


--
-- Name: flow_subscriptions platform_update; Type: POLICY; Schema: oryh; Owner: -
--

CREATE POLICY platform_update ON oryh.flow_subscriptions FOR UPDATE USING ((((tenant_id)::text = current_setting('app.tenant_id'::text, true)) OR (current_setting('app.is_platform_admin'::text, true) = 'on'::text))) WITH CHECK ((((tenant_id)::text = current_setting('app.tenant_id'::text, true)) OR (current_setting('app.is_platform_admin'::text, true) = 'on'::text)));


--
-- Name: flow_runs platform_write; Type: POLICY; Schema: oryh; Owner: -
--

CREATE POLICY platform_write ON oryh.flow_runs FOR INSERT WITH CHECK ((((tenant_id)::text = current_setting('app.tenant_id'::text, true)) OR (current_setting('app.is_platform_admin'::text, true) = 'on'::text)));


--
-- Name: flow_subscriptions platform_write; Type: POLICY; Schema: oryh; Owner: -
--

CREATE POLICY platform_write ON oryh.flow_subscriptions FOR INSERT WITH CHECK ((((tenant_id)::text = current_setting('app.tenant_id'::text, true)) OR (current_setting('app.is_platform_admin'::text, true) = 'on'::text)));


--
-- Name: policies; Type: ROW SECURITY; Schema: oryh; Owner: -
--

ALTER TABLE oryh.policies ENABLE ROW LEVEL SECURITY;

--
-- Name: product_prices; Type: ROW SECURITY; Schema: oryh; Owner: -
--

ALTER TABLE oryh.product_prices ENABLE ROW LEVEL SECURITY;

--
-- Name: product_skus; Type: ROW SECURITY; Schema: oryh; Owner: -
--

ALTER TABLE oryh.product_skus ENABLE ROW LEVEL SECURITY;

--
-- Name: products; Type: ROW SECURITY; Schema: oryh; Owner: -
--

ALTER TABLE oryh.products ENABLE ROW LEVEL SECURITY;

--
-- Name: projects; Type: ROW SECURITY; Schema: oryh; Owner: -
--

ALTER TABLE oryh.projects ENABLE ROW LEVEL SECURITY;

--
-- Name: purchase_order_adjustments; Type: ROW SECURITY; Schema: oryh; Owner: -
--

ALTER TABLE oryh.purchase_order_adjustments ENABLE ROW LEVEL SECURITY;

--
-- Name: purchase_order_items; Type: ROW SECURITY; Schema: oryh; Owner: -
--

ALTER TABLE oryh.purchase_order_items ENABLE ROW LEVEL SECURITY;

--
-- Name: purchase_orders; Type: ROW SECURITY; Schema: oryh; Owner: -
--

ALTER TABLE oryh.purchase_orders ENABLE ROW LEVEL SECURITY;

--
-- Name: purchase_request_items; Type: ROW SECURITY; Schema: oryh; Owner: -
--

ALTER TABLE oryh.purchase_request_items ENABLE ROW LEVEL SECURITY;

--
-- Name: purchase_requests; Type: ROW SECURITY; Schema: oryh; Owner: -
--

ALTER TABLE oryh.purchase_requests ENABLE ROW LEVEL SECURITY;

--
-- Name: resource_bookings; Type: ROW SECURITY; Schema: oryh; Owner: -
--

ALTER TABLE oryh.resource_bookings ENABLE ROW LEVEL SECURITY;

--
-- Name: resources; Type: ROW SECURITY; Schema: oryh; Owner: -
--

ALTER TABLE oryh.resources ENABLE ROW LEVEL SECURITY;

--
-- Name: roles; Type: ROW SECURITY; Schema: oryh; Owner: -
--

ALTER TABLE oryh.roles ENABLE ROW LEVEL SECURITY;

--
-- Name: sales_order_adjustments; Type: ROW SECURITY; Schema: oryh; Owner: -
--

ALTER TABLE oryh.sales_order_adjustments ENABLE ROW LEVEL SECURITY;

--
-- Name: sales_order_items; Type: ROW SECURITY; Schema: oryh; Owner: -
--

ALTER TABLE oryh.sales_order_items ENABLE ROW LEVEL SECURITY;

--
-- Name: sales_orders; Type: ROW SECURITY; Schema: oryh; Owner: -
--

ALTER TABLE oryh.sales_orders ENABLE ROW LEVEL SECURITY;

--
-- Name: sales_quotation_adjustments; Type: ROW SECURITY; Schema: oryh; Owner: -
--

ALTER TABLE oryh.sales_quotation_adjustments ENABLE ROW LEVEL SECURITY;

--
-- Name: sales_quotation_items; Type: ROW SECURITY; Schema: oryh; Owner: -
--

ALTER TABLE oryh.sales_quotation_items ENABLE ROW LEVEL SECURITY;

--
-- Name: sales_quotations; Type: ROW SECURITY; Schema: oryh; Owner: -
--

ALTER TABLE oryh.sales_quotations ENABLE ROW LEVEL SECURITY;

--
-- Name: supplier_products; Type: ROW SECURITY; Schema: oryh; Owner: -
--

ALTER TABLE oryh.supplier_products ENABLE ROW LEVEL SECURITY;

--
-- Name: api_keys tenant_insert; Type: POLICY; Schema: oryh; Owner: -
--

CREATE POLICY tenant_insert ON oryh.api_keys FOR INSERT WITH CHECK ((((tenant_id)::text = current_setting('app.tenant_id'::text, true)) OR (current_setting('app.is_platform_admin'::text, true) = 'on'::text)));


--
-- Name: users tenant_insert; Type: POLICY; Schema: oryh; Owner: -
--

CREATE POLICY tenant_insert ON oryh.users FOR INSERT WITH CHECK ((((tenant_id)::text = current_setting('app.tenant_id'::text, true)) OR (current_setting('app.is_platform_admin'::text, true) = 'on'::text)));


--
-- Name: approval_records tenant_isolation; Type: POLICY; Schema: oryh; Owner: -
--

CREATE POLICY tenant_isolation ON oryh.approval_records USING ((((tenant_id)::text = current_setting('app.tenant_id'::text, true)) OR (current_setting('app.is_platform_admin'::text, true) = 'on'::text))) WITH CHECK (((tenant_id)::text = current_setting('app.tenant_id'::text, true)));


--
-- Name: attachments tenant_isolation; Type: POLICY; Schema: oryh; Owner: -
--

CREATE POLICY tenant_isolation ON oryh.attachments USING ((((tenant_id)::text = current_setting('app.tenant_id'::text, true)) OR (current_setting('app.is_platform_admin'::text, true) = 'on'::text))) WITH CHECK (((tenant_id)::text = current_setting('app.tenant_id'::text, true)));


--
-- Name: audit_logs tenant_isolation; Type: POLICY; Schema: oryh; Owner: -
--

CREATE POLICY tenant_isolation ON oryh.audit_logs USING ((((tenant_id)::text = current_setting('app.tenant_id'::text, true)) OR (current_setting('app.is_platform_admin'::text, true) = 'on'::text))) WITH CHECK (((tenant_id)::text = current_setting('app.tenant_id'::text, true)));


--
-- Name: billing_account_entries tenant_isolation; Type: POLICY; Schema: oryh; Owner: -
--

CREATE POLICY tenant_isolation ON oryh.billing_account_entries USING ((((tenant_id)::text = current_setting('app.tenant_id'::text, true)) OR (current_setting('app.is_platform_admin'::text, true) = 'on'::text))) WITH CHECK (((tenant_id)::text = current_setting('app.tenant_id'::text, true)));


--
-- Name: billing_accounts tenant_isolation; Type: POLICY; Schema: oryh; Owner: -
--

CREATE POLICY tenant_isolation ON oryh.billing_accounts USING ((((tenant_id)::text = current_setting('app.tenant_id'::text, true)) OR (current_setting('app.is_platform_admin'::text, true) = 'on'::text))) WITH CHECK (((tenant_id)::text = current_setting('app.tenant_id'::text, true)));


--
-- Name: business_object_links tenant_isolation; Type: POLICY; Schema: oryh; Owner: -
--

CREATE POLICY tenant_isolation ON oryh.business_object_links USING ((((tenant_id)::text = current_setting('app.tenant_id'::text, true)) OR (current_setting('app.is_platform_admin'::text, true) = 'on'::text))) WITH CHECK (((tenant_id)::text = current_setting('app.tenant_id'::text, true)));


--
-- Name: business_objects tenant_isolation; Type: POLICY; Schema: oryh; Owner: -
--

CREATE POLICY tenant_isolation ON oryh.business_objects USING ((((tenant_id)::text = current_setting('app.tenant_id'::text, true)) OR (current_setting('app.is_platform_admin'::text, true) = 'on'::text))) WITH CHECK (((tenant_id)::text = current_setting('app.tenant_id'::text, true)));


--
-- Name: capabilities tenant_isolation; Type: POLICY; Schema: oryh; Owner: -
--

CREATE POLICY tenant_isolation ON oryh.capabilities USING ((((tenant_id)::text = current_setting('app.tenant_id'::text, true)) OR (current_setting('app.is_platform_admin'::text, true) = 'on'::text))) WITH CHECK (((tenant_id)::text = current_setting('app.tenant_id'::text, true)));


--
-- Name: customers tenant_isolation; Type: POLICY; Schema: oryh; Owner: -
--

CREATE POLICY tenant_isolation ON oryh.customers USING ((((tenant_id)::text = current_setting('app.tenant_id'::text, true)) OR (current_setting('app.is_platform_admin'::text, true) = 'on'::text))) WITH CHECK (((tenant_id)::text = current_setting('app.tenant_id'::text, true)));


--
-- Name: employees tenant_isolation; Type: POLICY; Schema: oryh; Owner: -
--

CREATE POLICY tenant_isolation ON oryh.employees USING ((((tenant_id)::text = current_setting('app.tenant_id'::text, true)) OR (current_setting('app.is_platform_admin'::text, true) = 'on'::text))) WITH CHECK (((tenant_id)::text = current_setting('app.tenant_id'::text, true)));


--
-- Name: expense_claims tenant_isolation; Type: POLICY; Schema: oryh; Owner: -
--

CREATE POLICY tenant_isolation ON oryh.expense_claims USING ((((tenant_id)::text = current_setting('app.tenant_id'::text, true)) OR (current_setting('app.is_platform_admin'::text, true) = 'on'::text))) WITH CHECK (((tenant_id)::text = current_setting('app.tenant_id'::text, true)));


--
-- Name: expense_items tenant_isolation; Type: POLICY; Schema: oryh; Owner: -
--

CREATE POLICY tenant_isolation ON oryh.expense_items USING ((((tenant_id)::text = current_setting('app.tenant_id'::text, true)) OR (current_setting('app.is_platform_admin'::text, true) = 'on'::text))) WITH CHECK (((tenant_id)::text = current_setting('app.tenant_id'::text, true)));


--
-- Name: inventory_item_details tenant_isolation; Type: POLICY; Schema: oryh; Owner: -
--

CREATE POLICY tenant_isolation ON oryh.inventory_item_details USING ((((tenant_id)::text = current_setting('app.tenant_id'::text, true)) OR (current_setting('app.is_platform_admin'::text, true) = 'on'::text))) WITH CHECK (((tenant_id)::text = current_setting('app.tenant_id'::text, true)));


--
-- Name: inventory_items tenant_isolation; Type: POLICY; Schema: oryh; Owner: -
--

CREATE POLICY tenant_isolation ON oryh.inventory_items USING ((((tenant_id)::text = current_setting('app.tenant_id'::text, true)) OR (current_setting('app.is_platform_admin'::text, true) = 'on'::text))) WITH CHECK (((tenant_id)::text = current_setting('app.tenant_id'::text, true)));


--
-- Name: invoice_items tenant_isolation; Type: POLICY; Schema: oryh; Owner: -
--

CREATE POLICY tenant_isolation ON oryh.invoice_items USING ((((tenant_id)::text = current_setting('app.tenant_id'::text, true)) OR (current_setting('app.is_platform_admin'::text, true) = 'on'::text))) WITH CHECK (((tenant_id)::text = current_setting('app.tenant_id'::text, true)));


--
-- Name: invoices tenant_isolation; Type: POLICY; Schema: oryh; Owner: -
--

CREATE POLICY tenant_isolation ON oryh.invoices USING ((((tenant_id)::text = current_setting('app.tenant_id'::text, true)) OR (current_setting('app.is_platform_admin'::text, true) = 'on'::text))) WITH CHECK (((tenant_id)::text = current_setting('app.tenant_id'::text, true)));


--
-- Name: object_type_definitions tenant_isolation; Type: POLICY; Schema: oryh; Owner: -
--

CREATE POLICY tenant_isolation ON oryh.object_type_definitions USING ((((tenant_id)::text = current_setting('app.tenant_id'::text, true)) OR (current_setting('app.is_platform_admin'::text, true) = 'on'::text))) WITH CHECK (((tenant_id)::text = current_setting('app.tenant_id'::text, true)));


--
-- Name: pay_histories tenant_isolation; Type: POLICY; Schema: oryh; Owner: -
--

CREATE POLICY tenant_isolation ON oryh.pay_histories USING ((((tenant_id)::text = current_setting('app.tenant_id'::text, true)) OR (current_setting('app.is_platform_admin'::text, true) = 'on'::text))) WITH CHECK (((tenant_id)::text = current_setting('app.tenant_id'::text, true)));


--
-- Name: payment_applications tenant_isolation; Type: POLICY; Schema: oryh; Owner: -
--

CREATE POLICY tenant_isolation ON oryh.payment_applications USING ((((tenant_id)::text = current_setting('app.tenant_id'::text, true)) OR (current_setting('app.is_platform_admin'::text, true) = 'on'::text))) WITH CHECK (((tenant_id)::text = current_setting('app.tenant_id'::text, true)));


--
-- Name: payments tenant_isolation; Type: POLICY; Schema: oryh; Owner: -
--

CREATE POLICY tenant_isolation ON oryh.payments USING ((((tenant_id)::text = current_setting('app.tenant_id'::text, true)) OR (current_setting('app.is_platform_admin'::text, true) = 'on'::text))) WITH CHECK (((tenant_id)::text = current_setting('app.tenant_id'::text, true)));


--
-- Name: policies tenant_isolation; Type: POLICY; Schema: oryh; Owner: -
--

CREATE POLICY tenant_isolation ON oryh.policies USING ((((tenant_id)::text = current_setting('app.tenant_id'::text, true)) OR (current_setting('app.is_platform_admin'::text, true) = 'on'::text))) WITH CHECK (((tenant_id)::text = current_setting('app.tenant_id'::text, true)));


--
-- Name: product_prices tenant_isolation; Type: POLICY; Schema: oryh; Owner: -
--

CREATE POLICY tenant_isolation ON oryh.product_prices USING ((((tenant_id)::text = current_setting('app.tenant_id'::text, true)) OR (current_setting('app.is_platform_admin'::text, true) = 'on'::text))) WITH CHECK (((tenant_id)::text = current_setting('app.tenant_id'::text, true)));


--
-- Name: product_skus tenant_isolation; Type: POLICY; Schema: oryh; Owner: -
--

CREATE POLICY tenant_isolation ON oryh.product_skus USING ((((tenant_id)::text = current_setting('app.tenant_id'::text, true)) OR (current_setting('app.is_platform_admin'::text, true) = 'on'::text))) WITH CHECK (((tenant_id)::text = current_setting('app.tenant_id'::text, true)));


--
-- Name: products tenant_isolation; Type: POLICY; Schema: oryh; Owner: -
--

CREATE POLICY tenant_isolation ON oryh.products USING ((((tenant_id)::text = current_setting('app.tenant_id'::text, true)) OR (current_setting('app.is_platform_admin'::text, true) = 'on'::text))) WITH CHECK (((tenant_id)::text = current_setting('app.tenant_id'::text, true)));


--
-- Name: projects tenant_isolation; Type: POLICY; Schema: oryh; Owner: -
--

CREATE POLICY tenant_isolation ON oryh.projects USING ((((tenant_id)::text = current_setting('app.tenant_id'::text, true)) OR (current_setting('app.is_platform_admin'::text, true) = 'on'::text))) WITH CHECK (((tenant_id)::text = current_setting('app.tenant_id'::text, true)));


--
-- Name: purchase_order_adjustments tenant_isolation; Type: POLICY; Schema: oryh; Owner: -
--

CREATE POLICY tenant_isolation ON oryh.purchase_order_adjustments USING ((((tenant_id)::text = current_setting('app.tenant_id'::text, true)) OR (current_setting('app.is_platform_admin'::text, true) = 'on'::text))) WITH CHECK (((tenant_id)::text = current_setting('app.tenant_id'::text, true)));


--
-- Name: purchase_order_items tenant_isolation; Type: POLICY; Schema: oryh; Owner: -
--

CREATE POLICY tenant_isolation ON oryh.purchase_order_items USING ((((tenant_id)::text = current_setting('app.tenant_id'::text, true)) OR (current_setting('app.is_platform_admin'::text, true) = 'on'::text))) WITH CHECK (((tenant_id)::text = current_setting('app.tenant_id'::text, true)));


--
-- Name: purchase_orders tenant_isolation; Type: POLICY; Schema: oryh; Owner: -
--

CREATE POLICY tenant_isolation ON oryh.purchase_orders USING ((((tenant_id)::text = current_setting('app.tenant_id'::text, true)) OR (current_setting('app.is_platform_admin'::text, true) = 'on'::text))) WITH CHECK (((tenant_id)::text = current_setting('app.tenant_id'::text, true)));


--
-- Name: purchase_request_items tenant_isolation; Type: POLICY; Schema: oryh; Owner: -
--

CREATE POLICY tenant_isolation ON oryh.purchase_request_items USING ((((tenant_id)::text = current_setting('app.tenant_id'::text, true)) OR (current_setting('app.is_platform_admin'::text, true) = 'on'::text))) WITH CHECK (((tenant_id)::text = current_setting('app.tenant_id'::text, true)));


--
-- Name: purchase_requests tenant_isolation; Type: POLICY; Schema: oryh; Owner: -
--

CREATE POLICY tenant_isolation ON oryh.purchase_requests USING ((((tenant_id)::text = current_setting('app.tenant_id'::text, true)) OR (current_setting('app.is_platform_admin'::text, true) = 'on'::text))) WITH CHECK (((tenant_id)::text = current_setting('app.tenant_id'::text, true)));


--
-- Name: resource_bookings tenant_isolation; Type: POLICY; Schema: oryh; Owner: -
--

CREATE POLICY tenant_isolation ON oryh.resource_bookings USING ((((tenant_id)::text = current_setting('app.tenant_id'::text, true)) OR (current_setting('app.is_platform_admin'::text, true) = 'on'::text))) WITH CHECK (((tenant_id)::text = current_setting('app.tenant_id'::text, true)));


--
-- Name: resources tenant_isolation; Type: POLICY; Schema: oryh; Owner: -
--

CREATE POLICY tenant_isolation ON oryh.resources USING ((((tenant_id)::text = current_setting('app.tenant_id'::text, true)) OR (current_setting('app.is_platform_admin'::text, true) = 'on'::text))) WITH CHECK (((tenant_id)::text = current_setting('app.tenant_id'::text, true)));


--
-- Name: roles tenant_isolation; Type: POLICY; Schema: oryh; Owner: -
--

CREATE POLICY tenant_isolation ON oryh.roles USING ((((tenant_id)::text = current_setting('app.tenant_id'::text, true)) OR (current_setting('app.is_platform_admin'::text, true) = 'on'::text))) WITH CHECK (((tenant_id)::text = current_setting('app.tenant_id'::text, true)));


--
-- Name: sales_order_adjustments tenant_isolation; Type: POLICY; Schema: oryh; Owner: -
--

CREATE POLICY tenant_isolation ON oryh.sales_order_adjustments USING ((((tenant_id)::text = current_setting('app.tenant_id'::text, true)) OR (current_setting('app.is_platform_admin'::text, true) = 'on'::text))) WITH CHECK (((tenant_id)::text = current_setting('app.tenant_id'::text, true)));


--
-- Name: sales_order_items tenant_isolation; Type: POLICY; Schema: oryh; Owner: -
--

CREATE POLICY tenant_isolation ON oryh.sales_order_items USING ((((tenant_id)::text = current_setting('app.tenant_id'::text, true)) OR (current_setting('app.is_platform_admin'::text, true) = 'on'::text))) WITH CHECK (((tenant_id)::text = current_setting('app.tenant_id'::text, true)));


--
-- Name: sales_orders tenant_isolation; Type: POLICY; Schema: oryh; Owner: -
--

CREATE POLICY tenant_isolation ON oryh.sales_orders USING ((((tenant_id)::text = current_setting('app.tenant_id'::text, true)) OR (current_setting('app.is_platform_admin'::text, true) = 'on'::text))) WITH CHECK (((tenant_id)::text = current_setting('app.tenant_id'::text, true)));


--
-- Name: sales_quotation_adjustments tenant_isolation; Type: POLICY; Schema: oryh; Owner: -
--

CREATE POLICY tenant_isolation ON oryh.sales_quotation_adjustments USING ((((tenant_id)::text = current_setting('app.tenant_id'::text, true)) OR (current_setting('app.is_platform_admin'::text, true) = 'on'::text))) WITH CHECK (((tenant_id)::text = current_setting('app.tenant_id'::text, true)));


--
-- Name: sales_quotation_items tenant_isolation; Type: POLICY; Schema: oryh; Owner: -
--

CREATE POLICY tenant_isolation ON oryh.sales_quotation_items USING ((((tenant_id)::text = current_setting('app.tenant_id'::text, true)) OR (current_setting('app.is_platform_admin'::text, true) = 'on'::text))) WITH CHECK (((tenant_id)::text = current_setting('app.tenant_id'::text, true)));


--
-- Name: sales_quotations tenant_isolation; Type: POLICY; Schema: oryh; Owner: -
--

CREATE POLICY tenant_isolation ON oryh.sales_quotations USING ((((tenant_id)::text = current_setting('app.tenant_id'::text, true)) OR (current_setting('app.is_platform_admin'::text, true) = 'on'::text))) WITH CHECK (((tenant_id)::text = current_setting('app.tenant_id'::text, true)));


--
-- Name: supplier_products tenant_isolation; Type: POLICY; Schema: oryh; Owner: -
--

CREATE POLICY tenant_isolation ON oryh.supplier_products USING ((((tenant_id)::text = current_setting('app.tenant_id'::text, true)) OR (current_setting('app.is_platform_admin'::text, true) = 'on'::text))) WITH CHECK (((tenant_id)::text = current_setting('app.tenant_id'::text, true)));


--
-- Name: tenant_skill_assignments tenant_isolation; Type: POLICY; Schema: oryh; Owner: -
--

CREATE POLICY tenant_isolation ON oryh.tenant_skill_assignments USING ((((tenant_id)::text = current_setting('app.tenant_id'::text, true)) OR (current_setting('app.is_platform_admin'::text, true) = 'on'::text))) WITH CHECK (((tenant_id)::text = current_setting('app.tenant_id'::text, true)));


--
-- Name: tenant_skills tenant_isolation; Type: POLICY; Schema: oryh; Owner: -
--

CREATE POLICY tenant_isolation ON oryh.tenant_skills USING ((((tenant_id)::text = current_setting('app.tenant_id'::text, true)) OR (current_setting('app.is_platform_admin'::text, true) = 'on'::text))) WITH CHECK (((tenant_id)::text = current_setting('app.tenant_id'::text, true)));


--
-- Name: timesheet_entries tenant_isolation; Type: POLICY; Schema: oryh; Owner: -
--

CREATE POLICY tenant_isolation ON oryh.timesheet_entries USING ((((tenant_id)::text = current_setting('app.tenant_id'::text, true)) OR (current_setting('app.is_platform_admin'::text, true) = 'on'::text))) WITH CHECK (((tenant_id)::text = current_setting('app.tenant_id'::text, true)));


--
-- Name: timesheet_headers tenant_isolation; Type: POLICY; Schema: oryh; Owner: -
--

CREATE POLICY tenant_isolation ON oryh.timesheet_headers USING ((((tenant_id)::text = current_setting('app.tenant_id'::text, true)) OR (current_setting('app.is_platform_admin'::text, true) = 'on'::text))) WITH CHECK (((tenant_id)::text = current_setting('app.tenant_id'::text, true)));


--
-- Name: todos tenant_isolation; Type: POLICY; Schema: oryh; Owner: -
--

CREATE POLICY tenant_isolation ON oryh.todos USING ((((tenant_id)::text = current_setting('app.tenant_id'::text, true)) OR (current_setting('app.is_platform_admin'::text, true) = 'on'::text))) WITH CHECK (((tenant_id)::text = current_setting('app.tenant_id'::text, true)));


--
-- Name: type_options tenant_isolation; Type: POLICY; Schema: oryh; Owner: -
--

CREATE POLICY tenant_isolation ON oryh.type_options USING ((((tenant_id)::text = current_setting('app.tenant_id'::text, true)) OR (current_setting('app.is_platform_admin'::text, true) = 'on'::text))) WITH CHECK (((tenant_id)::text = current_setting('app.tenant_id'::text, true)));


--
-- Name: vendors tenant_isolation; Type: POLICY; Schema: oryh; Owner: -
--

CREATE POLICY tenant_isolation ON oryh.vendors USING ((((tenant_id)::text = current_setting('app.tenant_id'::text, true)) OR (current_setting('app.is_platform_admin'::text, true) = 'on'::text))) WITH CHECK (((tenant_id)::text = current_setting('app.tenant_id'::text, true)));


--
-- Name: workflow_definitions tenant_isolation; Type: POLICY; Schema: oryh; Owner: -
--

CREATE POLICY tenant_isolation ON oryh.workflow_definitions USING ((((tenant_id)::text = current_setting('app.tenant_id'::text, true)) OR (current_setting('app.is_platform_admin'::text, true) = 'on'::text))) WITH CHECK (((tenant_id)::text = current_setting('app.tenant_id'::text, true)));


--
-- Name: flow_runs tenant_read; Type: POLICY; Schema: oryh; Owner: -
--

CREATE POLICY tenant_read ON oryh.flow_runs FOR SELECT USING ((((tenant_id)::text = current_setting('app.tenant_id'::text, true)) OR (current_setting('app.is_platform_admin'::text, true) = 'on'::text)));


--
-- Name: flow_subscriptions tenant_read; Type: POLICY; Schema: oryh; Owner: -
--

CREATE POLICY tenant_read ON oryh.flow_subscriptions FOR SELECT USING ((((tenant_id)::text = current_setting('app.tenant_id'::text, true)) OR (current_setting('app.is_platform_admin'::text, true) = 'on'::text)));


--
-- Name: tenant_skill_assignments; Type: ROW SECURITY; Schema: oryh; Owner: -
--

ALTER TABLE oryh.tenant_skill_assignments ENABLE ROW LEVEL SECURITY;

--
-- Name: tenant_skills; Type: ROW SECURITY; Schema: oryh; Owner: -
--

ALTER TABLE oryh.tenant_skills ENABLE ROW LEVEL SECURITY;

--
-- Name: api_keys tenant_update; Type: POLICY; Schema: oryh; Owner: -
--

CREATE POLICY tenant_update ON oryh.api_keys FOR UPDATE USING ((((tenant_id)::text = current_setting('app.tenant_id'::text, true)) OR (current_setting('app.is_platform_admin'::text, true) = 'on'::text))) WITH CHECK ((((tenant_id)::text = current_setting('app.tenant_id'::text, true)) OR (current_setting('app.is_platform_admin'::text, true) = 'on'::text)));


--
-- Name: users tenant_update; Type: POLICY; Schema: oryh; Owner: -
--

CREATE POLICY tenant_update ON oryh.users FOR UPDATE USING ((((tenant_id)::text = current_setting('app.tenant_id'::text, true)) OR (current_setting('app.is_platform_admin'::text, true) = 'on'::text))) WITH CHECK ((((tenant_id)::text = current_setting('app.tenant_id'::text, true)) OR (current_setting('app.is_platform_admin'::text, true) = 'on'::text)));


--
-- Name: timesheet_entries; Type: ROW SECURITY; Schema: oryh; Owner: -
--

ALTER TABLE oryh.timesheet_entries ENABLE ROW LEVEL SECURITY;

--
-- Name: timesheet_headers; Type: ROW SECURITY; Schema: oryh; Owner: -
--

ALTER TABLE oryh.timesheet_headers ENABLE ROW LEVEL SECURITY;

--
-- Name: todos; Type: ROW SECURITY; Schema: oryh; Owner: -
--

ALTER TABLE oryh.todos ENABLE ROW LEVEL SECURITY;

--
-- Name: type_options; Type: ROW SECURITY; Schema: oryh; Owner: -
--

ALTER TABLE oryh.type_options ENABLE ROW LEVEL SECURITY;

--
-- Name: users; Type: ROW SECURITY; Schema: oryh; Owner: -
--

ALTER TABLE oryh.users ENABLE ROW LEVEL SECURITY;

--
-- Name: vendors; Type: ROW SECURITY; Schema: oryh; Owner: -
--

ALTER TABLE oryh.vendors ENABLE ROW LEVEL SECURITY;

--
-- Name: workflow_definitions; Type: ROW SECURITY; Schema: oryh; Owner: -
--

ALTER TABLE oryh.workflow_definitions ENABLE ROW LEVEL SECURITY;

--
-- PostgreSQL database dump complete
--

