create table if not exists style_profiles (
    id uuid primary key default gen_random_uuid(),
    creator_handle text not null unique,
    hook_patterns jsonb not null default '[]',
    structure_notes text not null default '',
    tone_notes text not null default '',
    formatting_notes text not null default '',
    updated_at timestamptz not null default now()
);

create table if not exists drafts (
    id uuid primary key default gen_random_uuid(),
    slot integer not null,
    post_type text not null,
    body text not null,
    image_idea text,
    source_link text,
    status text not null default 'pending',
    created_at timestamptz not null default now()
);

create table if not exists leads (
    id uuid primary key default gen_random_uuid(),
    draft_id uuid references drafts (id),
    source text not null,
    detail text,
    created_at timestamptz not null default now()
);

create table if not exists reader_accounts (
    id uuid primary key default gen_random_uuid(),
    handle text not null unique,
    status text not null default 'warming',
    last_used_at timestamptz,
    failure_count integer not null default 0
);

create table if not exists check_ins (
    id uuid primary key default gen_random_uuid(),
    text text,
    created_at timestamptz not null default now()
);
