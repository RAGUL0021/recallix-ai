-- Recallix AI — schema, Row Level Security and storage policies.
-- Run once in Supabase Dashboard -> SQL Editor. Safe to re-run (idempotent where possible).

create extension if not exists vector with schema extensions;

-- ---------------------------------------------------------------- helpers
create or replace function public.set_updated_at() returns trigger
language plpgsql as $$
begin new.updated_at = now(); return new; end $$;

-- ---------------------------------------------------------------- profiles
create table if not exists public.profiles (
  id           uuid primary key references auth.users(id) on delete cascade,
  display_name text not null default '' check (char_length(display_name) <= 80),
  email        text not null default '',
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now()
);

create table if not exists public.user_preferences (
  user_id        uuid primary key references auth.users(id) on delete cascade,
  language       text not null default 'tanglish' check (language in ('english','tamil','tanglish')),
  level          text not null default 'beginner' check (level in ('beginner','intermediate','advanced')),
  voice_lang     text not null default 'en-IN' check (char_length(voice_lang) <= 12),
  auto_speak     boolean not null default false,
  history_limit  int not null default 10 check (history_limit between 2 and 30),
  updated_at     timestamptz not null default now()
);

-- Create profile + preferences automatically when a user signs up.
create or replace function public.handle_new_user() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  insert into public.profiles (id, display_name, email)
  values (new.id, coalesce(left(new.raw_user_meta_data->>'display_name', 80), ''), coalesce(new.email, ''))
  on conflict (id) do nothing;
  insert into public.user_preferences (user_id) values (new.id) on conflict do nothing;
  return new;
end $$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created after insert on auth.users
  for each row execute function public.handle_new_user();

-- ---------------------------------------------------------------- documents
create table if not exists public.documents (
  id            uuid primary key default gen_random_uuid(),
  owner_id      uuid not null references auth.users(id) on delete cascade,
  original_name text not null check (char_length(original_name) between 1 and 200),
  file_type     text not null check (file_type in
                  ('pdf','docx','pptx','text','markdown','rtf','code','csv','xlsx','image')),
  mime_type     text not null default 'application/octet-stream',
  size_bytes    bigint not null check (size_bytes >= 0),
  storage_path  text not null,
  sha256        text not null,
  status        text not null default 'processing'
                  check (status in ('processing','ready','needs_ocr','failed')),
  status_detail text not null default '',
  page_count    int not null default 0,
  is_favourite  boolean not null default false,
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now(),
  unique (owner_id, sha256)            -- duplicate upload protection per user
);
create index if not exists documents_owner_created_idx on public.documents (owner_id, created_at desc);
drop trigger if exists documents_updated on public.documents;
create trigger documents_updated before update on public.documents
  for each row execute function public.set_updated_at();

-- ---------------------------------------------------------------- chunks (RAG)
create table if not exists public.document_chunks (
  id           bigint generated always as identity primary key,
  document_id  uuid not null references public.documents(id) on delete cascade,
  owner_id     uuid not null references auth.users(id) on delete cascade,
  chunk_index  int not null,
  page_number  int not null,
  section      text not null default '',
  content      text not null,
  embedding    extensions.vector(768),
  created_at   timestamptz not null default now()
);
create index if not exists chunks_doc_page_idx on public.document_chunks (document_id, page_number);
create index if not exists chunks_owner_idx on public.document_chunks (owner_id);
create index if not exists chunks_embedding_idx on public.document_chunks
  using hnsw (embedding extensions.vector_cosine_ops);

-- ---------------------------------------------------------------- conversations
create table if not exists public.conversations (
  id          uuid primary key default gen_random_uuid(),
  owner_id    uuid not null references auth.users(id) on delete cascade,
  document_id uuid references public.documents(id) on delete set null,
  title       text not null default 'New conversation' check (char_length(title) <= 120),
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);
create index if not exists conversations_owner_idx on public.conversations (owner_id, updated_at desc);
drop trigger if exists conversations_updated on public.conversations;
create trigger conversations_updated before update on public.conversations
  for each row execute function public.set_updated_at();

create table if not exists public.messages (
  id              bigint generated always as identity primary key,
  conversation_id uuid not null references public.conversations(id) on delete cascade,
  owner_id        uuid not null references auth.users(id) on delete cascade,
  role            text not null check (role in ('user','assistant')),
  content         text not null check (char_length(content) <= 60000),
  language        text not null default 'english',
  sources         jsonb not null default '[]'::jsonb,
  created_at      timestamptz not null default now()
);
create index if not exists messages_conv_idx on public.messages (conversation_id, created_at);
create index if not exists messages_owner_idx on public.messages (owner_id);

create table if not exists public.saved_answers (
  id          bigint generated always as identity primary key,
  owner_id    uuid not null references auth.users(id) on delete cascade,
  document_id uuid references public.documents(id) on delete set null,
  title       text not null default '' check (char_length(title) <= 120),
  content     text not null check (char_length(content) <= 60000),
  created_at  timestamptz not null default now()
);
create index if not exists saved_answers_owner_idx on public.saved_answers (owner_id, created_at desc);

create table if not exists public.saved_diagrams (
  id           bigint generated always as identity primary key,
  owner_id     uuid not null references auth.users(id) on delete cascade,
  title        text not null default '' check (char_length(title) <= 120),
  mermaid_code text not null check (char_length(mermaid_code) <= 8000),
  created_at   timestamptz not null default now()
);
create index if not exists saved_diagrams_owner_idx on public.saved_diagrams (owner_id, created_at desc);

create table if not exists public.usage_events (
  id         bigint generated always as identity primary key,
  owner_id   uuid not null references auth.users(id) on delete cascade,
  kind       text not null check (kind in ('ai_chat','ai_diagram','ai_transcribe','embed_chunks','upload')),
  units      int not null default 1 check (units between 0 and 100000),
  created_at timestamptz not null default now()
);
create index if not exists usage_owner_time_idx on public.usage_events (owner_id, created_at desc);

-- ---------------------------------------------------------------- RLS
alter table public.profiles         enable row level security;
alter table public.user_preferences enable row level security;
alter table public.documents        enable row level security;
alter table public.document_chunks  enable row level security;
alter table public.conversations    enable row level security;
alter table public.messages         enable row level security;
alter table public.saved_answers    enable row level security;
alter table public.saved_diagrams   enable row level security;
alter table public.usage_events     enable row level security;

-- profiles / preferences: own row only
drop policy if exists profiles_select on public.profiles;
drop policy if exists profiles_update on public.profiles;
create policy profiles_select on public.profiles for select to authenticated using (id = (select auth.uid()));
create policy profiles_update on public.profiles for update to authenticated
  using (id = (select auth.uid())) with check (id = (select auth.uid()));

drop policy if exists prefs_select on public.user_preferences;
drop policy if exists prefs_insert on public.user_preferences;
drop policy if exists prefs_update on public.user_preferences;
create policy prefs_select on public.user_preferences for select to authenticated using (user_id = (select auth.uid()));
create policy prefs_insert on public.user_preferences for insert to authenticated with check (user_id = (select auth.uid()));
create policy prefs_update on public.user_preferences for update to authenticated
  using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));

-- documents
drop policy if exists docs_select on public.documents;
drop policy if exists docs_insert on public.documents;
drop policy if exists docs_update on public.documents;
drop policy if exists docs_delete on public.documents;
create policy docs_select on public.documents for select to authenticated using (owner_id = (select auth.uid()));
create policy docs_insert on public.documents for insert to authenticated with check (owner_id = (select auth.uid()));
create policy docs_update on public.documents for update to authenticated
  using (owner_id = (select auth.uid())) with check (owner_id = (select auth.uid()));
create policy docs_delete on public.documents for delete to authenticated using (owner_id = (select auth.uid()));

-- chunks: owner AND the parent document must belong to the same owner
drop policy if exists chunks_select on public.document_chunks;
drop policy if exists chunks_insert on public.document_chunks;
drop policy if exists chunks_delete on public.document_chunks;
drop policy if exists chunks_update on public.document_chunks;
create policy chunks_select on public.document_chunks for select to authenticated using (owner_id = (select auth.uid()));
create policy chunks_insert on public.document_chunks for insert to authenticated
  with check (owner_id = (select auth.uid())
    and exists (select 1 from public.documents d where d.id = document_id and d.owner_id = (select auth.uid())));
create policy chunks_delete on public.document_chunks for delete to authenticated using (owner_id = (select auth.uid()));
create policy chunks_update on public.document_chunks for update to authenticated
  using (owner_id = (select auth.uid())) with check (owner_id = (select auth.uid()));

-- conversations
drop policy if exists conv_select on public.conversations;
drop policy if exists conv_insert on public.conversations;
drop policy if exists conv_update on public.conversations;
drop policy if exists conv_delete on public.conversations;
create policy conv_select on public.conversations for select to authenticated using (owner_id = (select auth.uid()));
create policy conv_insert on public.conversations for insert to authenticated
  with check (owner_id = (select auth.uid())
    and (document_id is null or exists (select 1 from public.documents d where d.id = document_id and d.owner_id = (select auth.uid()))));
create policy conv_update on public.conversations for update to authenticated
  using (owner_id = (select auth.uid())) with check (owner_id = (select auth.uid()));
create policy conv_delete on public.conversations for delete to authenticated using (owner_id = (select auth.uid()));

-- messages
drop policy if exists msg_select on public.messages;
drop policy if exists msg_insert on public.messages;
drop policy if exists msg_delete on public.messages;
create policy msg_select on public.messages for select to authenticated using (owner_id = (select auth.uid()));
create policy msg_insert on public.messages for insert to authenticated
  with check (owner_id = (select auth.uid())
    and exists (select 1 from public.conversations c where c.id = conversation_id and c.owner_id = (select auth.uid())));
create policy msg_delete on public.messages for delete to authenticated using (owner_id = (select auth.uid()));

-- saved answers / diagrams
drop policy if exists sa_select on public.saved_answers;
drop policy if exists sa_insert on public.saved_answers;
drop policy if exists sa_delete on public.saved_answers;
create policy sa_select on public.saved_answers for select to authenticated using (owner_id = (select auth.uid()));
create policy sa_insert on public.saved_answers for insert to authenticated with check (owner_id = (select auth.uid()));
create policy sa_delete on public.saved_answers for delete to authenticated using (owner_id = (select auth.uid()));

drop policy if exists sd_select on public.saved_diagrams;
drop policy if exists sd_insert on public.saved_diagrams;
drop policy if exists sd_delete on public.saved_diagrams;
create policy sd_select on public.saved_diagrams for select to authenticated using (owner_id = (select auth.uid()));
create policy sd_insert on public.saved_diagrams for insert to authenticated with check (owner_id = (select auth.uid()));
create policy sd_delete on public.saved_diagrams for delete to authenticated using (owner_id = (select auth.uid()));

-- usage events: append-only (no update, no delete) so users cannot reset their own quota
drop policy if exists ue_select on public.usage_events;
drop policy if exists ue_insert on public.usage_events;
create policy ue_select on public.usage_events for select to authenticated using (owner_id = (select auth.uid()));
create policy ue_insert on public.usage_events for insert to authenticated with check (owner_id = (select auth.uid()));

-- ---------------------------------------------------------------- vector search (SECURITY INVOKER => RLS applies)
create or replace function public.match_chunks(
  query_embedding extensions.vector(768),
  p_document_id uuid,
  match_count int default 6
) returns table (id bigint, page_number int, section text, content text, similarity float)
language sql stable security invoker set search_path = public, extensions as $$
  select c.id, c.page_number, c.section, c.content,
         1 - (c.embedding <=> query_embedding) as similarity
  from public.document_chunks c
  where c.document_id = p_document_id
    and c.owner_id = auth.uid()
    and c.embedding is not null
  order by c.embedding <=> query_embedding
  limit least(greatest(match_count, 1), 20);
$$;
revoke all on function public.match_chunks from public, anon;
grant execute on function public.match_chunks to authenticated;

-- ---------------------------------------------------------------- storage (private bucket, per-user folder)
insert into storage.buckets (id, name, public, file_size_limit)
values ('documents', 'documents', false, 26214400)
on conflict (id) do update set public = false, file_size_limit = 26214400;

drop policy if exists "documents read own"   on storage.objects;
drop policy if exists "documents insert own" on storage.objects;
drop policy if exists "documents update own" on storage.objects;
drop policy if exists "documents delete own" on storage.objects;
create policy "documents read own" on storage.objects for select to authenticated
  using (bucket_id = 'documents' and (storage.foldername(name))[1] = (select auth.uid())::text);
create policy "documents insert own" on storage.objects for insert to authenticated
  with check (bucket_id = 'documents' and (storage.foldername(name))[1] = (select auth.uid())::text);
create policy "documents update own" on storage.objects for update to authenticated
  using (bucket_id = 'documents' and (storage.foldername(name))[1] = (select auth.uid())::text);
create policy "documents delete own" on storage.objects for delete to authenticated
  using (bucket_id = 'documents' and (storage.foldername(name))[1] = (select auth.uid())::text);
