BEGIN;

CREATE SCHEMA znuny;
COMMENT ON SCHEMA znuny IS 'znuny-schema-v1';

CREATE TABLE znuny.lotes_importacao (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    fingerprint_sha256 text NOT NULL UNIQUE
        CHECK (fingerprint_sha256 ~ '^[0-9a-f]{64}$'),
    importado_em timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    arquivos jsonb NOT NULL CHECK (jsonb_typeof(arquivos) = 'array'),
    resumo_qualidade jsonb NOT NULL CHECK (jsonb_typeof(resumo_qualidade) = 'object')
);

CREATE TABLE znuny.chamados (
    lote_id bigint NOT NULL REFERENCES znuny.lotes_importacao (id),
    numero_chamado text NOT NULL
        CHECK (numero_chamado <> '' AND numero_chamado = btrim(numero_chamado)),
    criado_em timestamp,
    fechado_em timestamp,
    primeira_resposta_em timestamp,
    primeiro_bloqueio_em timestamp,
    estado text,
    fila text,
    prioridade text,
    tempo_solucao_informado_min numeric CHECK (tempo_solucao_informado_min >= 0),
    tempo_fechamento_corrido_min numeric CHECK (tempo_fechamento_corrido_min >= 0),
    tempo_primeira_resposta_corrido_min numeric CHECK (tempo_primeira_resposta_corrido_min >= 0),
    PRIMARY KEY (lote_id, numero_chamado)
);

COMMENT ON COLUMN znuny.chamados.criado_em IS
    'Horário registrado na exportação. Fuso ainda não confirmado.';

CREATE TABLE znuny.chamados_origem (
    lote_id bigint NOT NULL,
    numero_chamado text NOT NULL,
    arquivo text NOT NULL CHECK (btrim(arquivo) <> ''),
    ocorrencias integer NOT NULL CHECK (ocorrencias > 0),
    PRIMARY KEY (lote_id, numero_chamado, arquivo),
    FOREIGN KEY (lote_id, numero_chamado) REFERENCES znuny.chamados (lote_id, numero_chamado)
);

COMMIT;
