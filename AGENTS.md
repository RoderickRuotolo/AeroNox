# AGENTS.md — AeroNox

## Context

Leia `SPEC.md` antes de implementar qualquer tarefa. O AeroNox é um gerenciador Linux de temas noturnos coordenados (Aviation Red e NVIS Green A inspired) para Terminator, htop, Vim e VS Code. Esta versão do documento descreve um **MVP**, não um produto pronto.

## Prioridades

1. Segurança e reversibilidade > cobertura de recursos > estética.
2. Não sobrescrever arquivos pessoais ou configurações de usuário sem backup, dry-run e controle de conflitos.
3. Todos os testes devem rodar em HOME/XDG temporários, nunca sobre dotfiles reais.
4. Respeitar o escopo: VS Code assistido no MVP; troca automática de janelas abertas é futura.
5. Manter as duas paletas centralizadas em `palettes/*.json`, com validação.

## Stack e padrões

- Python >= 3.11; `src/` layout; type hints; interfaces pequenas; dependências mínimas.
- CLI `aeronox`; `pytest` para testes e `ruff` para lint.
- Python em inglês, comandos e documentação claros; nenhuma telemetria ou rede em runtime.
- Nunca usar `shell=True` para executar comandos de usuário; não instalar com `sudo`.
- Para Terminator, usar parser próprio para ConfigObj ou dependência adequada; não tratar o arquivo como INI plano.
- Backups/manifest fora do repositório, respeitando XDG; operações atômicas e rollback sempre que necessário.

## Fluxo de trabalho

1. Leia a seção relevante de `SPEC.md`.
2. Proponha brevemente o que mudará e delimite o PR/etapa.
3. Escreva testes antes ou junto das alterações.
4. Implemente mudanças pequenas e documente as limitações técnicas.
5. Rode `ruff check .` e `pytest` (se a ferramenta estiver instalada); corrija falhas ou relate impedimentos reais.
6. Ao terminar, resuma arquivos alterados, testes executados, riscos e próximas etapas.

## Restrições de segurança

- Não apagar, renomear ou substituir o `default` do Terminator.
- Não tocar em `.vimrc`, `.bashrc`, `.zshrc` ou VS Code `Default` automaticamente no MVP.
- Não remover arquivos alterados pelo usuário desde a instalação.
- Não fazer alegações de certificação NVIS ou benefícios médicos comprovados.
- Não usar arquivos reais do `$HOME` do desenvolvedor como fixtures.

## Critério de conclusão

Consulte os critérios de aceite e cenários E2E das seções 9 e 10 de `SPEC.md`. Uma funcionalidade só está pronta quando seu comportamento é testado e sua limitação documentada.
