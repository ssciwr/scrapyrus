CREATE TABLE IF NOT EXISTS papyri (
    source_path text NOT NULL PRIMARY KEY,
    tm_id integer NOT NULL,
    dclp_id integer,
    dclp_hybrid_id text,
    ddb_perseus_style_id text,
    ddb_filename text,
    ddb_hybrid_id text,
    hgv_id text,
    ldab_id text,
    mp3_id text,
    title text,
    material text,
    current_location text
);

CREATE INDEX IF NOT EXISTS papyri_tm_id_idx ON papyri (tm_id);
