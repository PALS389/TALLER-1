-- =====================================================================
-- RadVol3D · Layer 4 · Database schema
-- Target: PostgreSQL 15+ (Supabase).
-- Run once, in full, from the Supabase SQL Editor.
--
-- Naming: the ER model documents attributes in camelCase (studyCode);
-- SQL uses snake_case (study_code) so that no identifier needs quoting.
--
-- Domain values (status, stage names, organ names) are kept in Spanish
-- because they are data defined by the ER model, not code.
-- =====================================================================

-- ---------------------------------------------------------------------
-- 1. patient
-- Only an internal code is stored. No name, no document, no personal data.
-- birth_date and sex are optional: the current web interface does not
-- collect patient data yet, so studies are linked to a placeholder row.
-- ---------------------------------------------------------------------
create table patient (
  patient_code  varchar(10) primary key
                check (patient_code ~ '^PAC[0-9]{6}$'),
  birth_date    date,
  sex           char(1) check (sex in ('F', 'M'))
);

-- ---------------------------------------------------------------------
-- 2. organ
-- Closed set of organs the system works on.
-- ---------------------------------------------------------------------
create table organ (
  organ_id           smallint generated always as identity primary key,
  organ_name         varchar(30) not null unique,
  anatomical_region  varchar(40) not null
);

-- ---------------------------------------------------------------------
-- 3. model
-- Records which model (or method) produced each result.
-- organ_id is null for the reconstruction model, which serves both organs.
-- weights_path and trained_on are null for methods that are not trained,
-- such as plain back-projection.
-- ---------------------------------------------------------------------
create table model (
  model_id      smallint generated always as identity primary key,
  organ_id      smallint references organ (organ_id),
  model_name    varchar(60) not null,
  model_type    varchar(16) not null
                check (model_type in ('reconstruccion', 'segmentacion')),
  version       varchar(10) not null,
  weights_path  varchar(255),
  trained_on    date,
  unique (model_name, version)
);

-- ---------------------------------------------------------------------
-- 4. study
-- The unit of work: one set of radiographs that is processed and reported.
--
-- study_code accepts the identifiers the business layer produces:
-- a user-supplied one such as 'lung_003', or a generated one such as
-- 'EST-20261006-184530-a1b2'.
--
-- psnr, ssim and dice are only filled for validation cases that have a
-- reference CT volume. volume_min/max/mean describe the reconstructed
-- volume and are filled once processing finishes.
-- ---------------------------------------------------------------------
create table study (
  study_code      varchar(64) primary key
                  check (study_code ~ '^[A-Za-z0-9_-]{1,64}$'),
  patient_code    varchar(10) not null references patient (patient_code),
  organ_id        smallint    not null references organ (organ_id),
  date_time       timestamp   not null,
  status          varchar(12) not null default 'pendiente'
                  check (status in ('pendiente', 'procesando', 'completado', 'error')),
  psnr            numeric(6, 2),
  ssim            numeric(4, 3) check (ssim between 0 and 1),
  dice            numeric(4, 3) check (dice between 0 and 1),
  total_time_sec  numeric(9, 3),
  volume_min      numeric(12, 4),
  volume_max      numeric(12, 4),
  volume_mean     numeric(12, 4)
);

-- ---------------------------------------------------------------------
-- 5. projection
-- One row per radiograph. file_path is where the image is stored;
-- original_name is the file name the user uploaded, which the interface
-- shows back.
--
-- The (study_code, angle_degrees) pair is a candidate key: a study cannot
-- hold two radiographs taken at the same angle.
-- ---------------------------------------------------------------------
create table projection (
  projection_id  integer generated always as identity primary key,
  study_code     varchar(64)  not null references study (study_code) on delete cascade,
  angle_degrees  smallint     not null check (angle_degrees in (0, 45, 90, 135)),
  file_path      varchar(255) not null,
  original_name  varchar(255) not null,
  unique (study_code, angle_degrees)
);

-- ---------------------------------------------------------------------
-- 6. processing_stage
-- The four pipeline stages whose progress the interface shows.
-- model_id is null for stages that use no model.
-- finished_at is null while the stage is still running.
-- ---------------------------------------------------------------------
create table processing_stage (
  stage_id      integer generated always as identity primary key,
  study_code    varchar(64) not null references study (study_code) on delete cascade,
  model_id      smallint    references model (model_id),
  stage_number  smallint    not null check (stage_number between 1 and 4),
  stage_name    varchar(40) not null
                check (stage_name in ('Preprocesamiento', 'Reconstrucción',
                                      'Segmentación', 'Mallas')),
  started_at    timestamp   not null,
  finished_at   timestamp,
  stage_status  varchar(12) not null default 'en espera'
                check (stage_status in ('en espera', 'ejecutando', 'completada',
                                        'omitida', 'error')),
  unique (study_code, stage_number)
);

-- ---------------------------------------------------------------------
-- 7. lesion
-- A study may yield no lesion, one, or several.
-- ---------------------------------------------------------------------
create table lesion (
  lesion_id        integer generated always as identity primary key,
  study_code       varchar(64)  not null references study (study_code) on delete cascade,
  volume_cm3       numeric(8, 1) not null,
  max_diameter_mm  numeric(6, 1) not null,
  location         varchar(60)  not null,
  confidence       numeric(3, 2) not null check (confidence between 0 and 1),
  mesh_path        varchar(255)
);

-- ---------------------------------------------------------------------
-- Indexes on the foreign keys that are queried the most.
-- ---------------------------------------------------------------------
create index idx_study_patient on study (patient_code);
create index idx_study_organ   on study (organ_id);
create index idx_lesion_study  on lesion (study_code);
create index idx_stage_model   on processing_stage (model_id);
create index idx_model_organ   on model (organ_id);

-- ---------------------------------------------------------------------
-- Row Level Security blocks every read and write through Supabase's
-- public API. The persistence layer connects straight to PostgreSQL,
-- which is not affected by these policies.
-- ---------------------------------------------------------------------
alter table patient          enable row level security;
alter table organ            enable row level security;
alter table model            enable row level security;
alter table study            enable row level security;
alter table projection       enable row level security;
alter table processing_stage enable row level security;
alter table lesion           enable row level security;

-- ---------------------------------------------------------------------
-- Seed data
-- ---------------------------------------------------------------------

-- The two organs shown by the interface.
insert into organ (organ_name, anatomical_region) values
  ('Pulmón', 'tórax'),
  ('Hígado', 'abdomen superior');

-- Placeholder patient. The interface does not collect patient data yet,
-- so every study is linked here until it does.
insert into patient (patient_code) values ('PAC000000');