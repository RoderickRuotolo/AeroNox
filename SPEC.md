# AeroNox — Especificação funcional e técnica

> **Status:** proposta de implementação · **Versão do documento:** 0.1 · **Data:** 2026-10-23  
> **Tagline:** *Coordinated low-light themes for Linux developer tools.*  
> **Público:** desenvolvedores Linux que usam aplicações de terminal e editores à noite.

## 1. Visão geral

O **AeroNox** é um projeto open source que oferece paletas noturnas **consistentes, não destrutivas e reversíveis** para ferramentas de desenvolvimento no Linux. Os primeiros temas são **Aviation Red** e **NVIS Green A (inspired)**; os aplicativos-alvo são **Terminator, htop, Vim e Visual Studio Code**.

A experiência desejada é aplicar uma paleta central, abrir as ferramentas com a aparência correspondente e retornar ao visual anterior sem perder fontes, atalhos, layouts, plugins, históricos ou outras preferências pessoais.

### Princípios inegociáveis

1. **Não destruir ou sobrescrever configurações pessoais**; criar perfis, recursos separados e cópias de segurança.
2. **Reversibilidade verificável**: `restore` e `uninstall` não podem apagar mudanças feitas pelo usuário após a instalação sem consentimento explícito.
3. **Transparência**: `--dry-run` apresenta mudanças planejadas antes de alterar arquivos.
4. **Privilégios mínimos**: instalar em modo usuário, sem `sudo`, sem telemetria e sem rede obrigatória.
5. **Uma fonte de verdade para as cores**: todos os adapters leem as mesmas definições semânticas e ANSI.
6. **Acessibilidade e segurança da informação**: monocromia não deve ser o único sinal de erro/sucesso.
7. **Compatibilidade incremental**: aplicativos não instalados são ignorados com aviso, não causam falha geral.

**Limite das alegações:** os temas são **inspirados** em iluminação aeronáutica e NVIS; um monitor RGB comum NÃO é certificado NVIS, NÃO garante compatibilidade com óculos de visão noturna e NÃO comprova benefício médico/oftalmológico. A intensidade do brilho, o ambiente e a calibração da tela importam.

## 2. Escopo e fases

### MVP — v0.1 (obrigatório)

- CLI `aeronox` para Linux, com `doctor`, `palette list/show`, `install`, `apply`, `current`, `open`, `backup list`, `restore`, `uninstall`, `--dry-run` e `--version`.
- Gerador de perfis **Terminator** que **preserva o `default`** e cria perfis próprios.
- Geração de esquemas de cores **Vim** separados das configurações existentes.
- Integração **htop** usando `HTOPRC` e variante monocromática ou de baixo cromatismo, sem prometer correspondência RGB completa.
- Gerar **artefatos/guia de configuração para VS Code** e permitir iniciar perfis já configurados; importação/configuração pode ser manual no MVP.
- Estado persistente de tema atual e wrappers de inicialização que usam esse estado.
- Backups locais, operações atômicas, restauração conservadora, detecção de conflitos e testes automatizados.
- README em inglês, instruções em português brasileiro (opcional tradução posterior) e screenshots de demonstração identificados como *mockups* quando aplicável.

### v0.2 (posterior; NÃO bloquear o MVP)

- Integração completa do VS Code via extensão própria contendo os dois temas (workbench, tokens TextMate, semantic tokens e terminal ANSI), com instruções claras de instalação; considerar VSIX.
- Opcionalmente, extensão para observar o arquivo de estado do AeroNox e aplicar o tema **somente após opt-in explícito**, preservando/restaurando o tema anterior de cada perfil.
- Importação assistida de configurações sem reescrever `settings.json` arbitrariamente.

### v0.3+ (fora do escopo imediato)

- Atualização automática de janelas já abertas quando suportado; UI TUI; GTK/KDE, Neovim, tmux, Zsh, Alacritty, Kitty, JetBrains; modos horários; integração com brilho do monitor.
- Nunca implementar ajuste automático de brilho ou troca de configurações do desktop como efeito colateral do MVP.

## 3. Público, ambiente e requisitos

- Alvo primário: **Ubuntu Desktop** recente, mas evitar dependência da distribuição; expandir para Linux em geral.
- Python 3.11+; instalação recomendada via **pipx** (ou `uv tool install`).
- Dependências de runtime mínimas; analisar `configobj` para editar corretamente o formato do Terminator sem descartar seções desconhecidas.
- Respeitar `XDG_CONFIG_HOME`, `XDG_STATE_HOME` e `XDG_DATA_HOME` com os respectivos defaults do padrão XDG.
- Não instalar o Terminator, htop, Vim ou VS Code automaticamente.
- Detectar comandos e versões disponíveis; relatar limitações de variantes Snap, Flatpak, Insiders e VSCodium sem escrever em diretórios desconhecidos.
- Todo comando deve funcionar sem conexão com a internet depois da instalação.

## 4. Paletas: fonte única de verdade

Manter `palettes/aviation-red.json` e `palettes/nvis-green-a.json` com schema versionado. As cores abaixo são **ponto de partida visual**, ajustáveis após testes reais, NÃO especificações espectrais.

| Papel | Aviation Red | NVIS Green A inspired |
|---|---|---|
| background | `#050000` | `#000500` |
| background_alt | `#140303` | `#031408` |
| foreground | `#CC3333` | `#66BB66` |
| foreground_muted | `#8F2424` | `#397A43` |
| accent | `#FF4545` | `#88DD88` |
| cursor | `#DD3333` | `#66CC77` |
| selection | `#421010` | `#123A1B` |

Cada JSON deve fornecer:

```json
{
  "schema_version": 1,
  "id": "aviation-red",
  "name": "Aviation Red",
  "description": "Low-light red monochromatic palette",
  "colors": {
    "background": "#050000",
    "background_alt": "#140303",
    "foreground": "#CC3333",
    "foreground_muted": "#8F2424",
    "accent": "#FF4545",
    "cursor": "#DD3333",
    "selection": "#421010"
  },
  "ansi16": ["#050000", "#641818", "#7B2424", "#99302B", "#592121", "#8B3434", "#AA4840", "#C45A52", "#4A1717", "#D43B3B", "#B5473B", "#CC5B45", "#A95151", "#DA6262", "#E67769", "#F09989"]
}
```

Para `nvis-green-a`, usar `ansi16` inicial:

```json
["#000500", "#1C4D29", "#235C32", "#356B3E", "#28563A", "#3F6B45", "#498253", "#6FA879", "#193B20", "#3D8950", "#51A366", "#66B775", "#4A9465", "#79C589", "#8CD49B", "#ACDDB4"]
```

**Validação:** exatamente 16 entradas ANSI; todos os valores em hex RGB válido, IDs estáveis, chaves obrigatórias; contraste reportado por script, sem alegação de certificação. No modo monocromático, cores ANSI originalmente destinadas a “vermelho”, “verde” etc. deixam de representar semanticamente essas categorias: destacar isso na documentação e usar texto/ícones para situações críticas.

## 5. Experiência do usuário (CLI)

O executável deve expor:

```bash
aeronox doctor
aeronox palette list
aeronox palette show aviation-red
aeronox install --dry-run
aeronox install --components terminator,htop,vim,vscode
aeronox apply aviation-red --dry-run
aeronox apply aviation-red
aeronox apply nvis-green-a
aeronox current
aeronox open terminator
aeronox open htop
aeronox open vim -- README.md
aeronox open code -- ~/projetos/meu-projeto
aeronox backup list
aeronox restore --dry-run
aeronox restore
aeronox uninstall --dry-run
aeronox uninstall
```

**Semântica:**

- `install`: preparar recursos do AeroNox, sem alterar o tema padrão dos aplicativos. É idempotente. Exibir quais integrações foram instaladas, omitidas ou exigem ações manuais.
- `apply <palette>`: alterar **apenas o estado ativo do AeroNox**; perfis/cores serão usados nas **novas sessões abertas pelos wrappers**. Não prometer mudança instantânea de aplicativos abertos.
- `open terminator`: executar `terminator -p "AeroNox Aviation Red"` ou equivalente verde, respeitando o estado ativo. Na ausência de tema ativo, iniciar normalmente.
- `open htop`: definir `HTOPRC` apontando para uma cópia gerenciada do `htoprc` e executar `htop`; se a integração não estiver pronta, diagnóstico acionável. `htop -C` pode ser modo de fallback, após teste de legibilidade.
- `open vim -- args`: iniciar Vim com o esquema via parâmetro de inicialização **sem alterar `.vimrc`**; por exemplo, estratégia compatível com `-c 'colorscheme aeronox_red'` validada em testes. Passar argumentos do usuário sem concatená-los em uma string de shell.
- `open code -- args`: iniciar `code --profile "AeroNox Aviation Red"` apenas quando o perfil estiver configurado; **não assumir que `--profile` importa automaticamente as cores**. Se faltar configuração, exibir passos manuais ou integração pendente. Não forçar criação de perfil vazio sem aviso.
- `restore`: voltar o **estado ativo** ao modo `original` e retornar aos comandos/wrappers não tematizados; perfis AeroNox continuam disponíveis até `uninstall`. Não reescrever o tema pessoal original sem necessidade.
- `uninstall`: remover SOMENTE recursos de propriedade do AeroNox quando não modificados pelo usuário; preservar quaisquer alterações externas e relatar conflitos.
- `doctor`: indicar aplicações disponíveis, caminho de config, suporte a terminal True Color, detecção de perfil VS Code e detalhes de plataforma, sem expor dados privados em logs por padrão.
- `--dry-run`: nenhuma alteração de disco ou processos; saída com plano, diffs limitados e caminhos-alvo (ocultar conteúdo sensível).
- Saídas e códigos: sucesso 0; falha operacional diferente de 0; incompatibilidade parcial deve ser avisada com status por adapter.

O usuário também deve conseguir continuar usando `terminator`, `htop`, `vim` e `code` normalmente fora dos wrappers. **Não criar aliases automaticamente**, não modificar PATH ou arquivos de inicialização de shell sem opt-in.

## 6. Contrato dos adapters

Definir uma interface pequena para cada integração:

```python
class Adapter(Protocol):
    name: str
    def detect(self) -> DetectionResult: ...
    def plan_install(self, palette_catalog: PaletteCatalog) -> list[PlannedChange]: ...
    def install(self, plan: list[PlannedChange]) -> InstallResult: ...
    def verify(self) -> VerificationResult: ...
    def plan_uninstall(self) -> list[PlannedChange]: ...
    def open_command(self, palette_id: str, args: list[str]) -> list[str]: ...
```

`PlannedChange` inclui caminho, ação (criar/atualizar/remover), origem esperada, ownership/manifest, motivo e regra de conflito. **Não executar operações via `shell=True`**. Usar `subprocess` com lista de argumentos e herdar o terminal interativo quando apropriado.

### 6.1 Terminator

- Ler configuração em `${XDG_CONFIG_HOME:-~/.config}/terminator/config`.
- Formato **ConfigObj**, com `[profiles]` e seções `[[nome]]`.
- Criar `AeroNox Aviation Red` e `AeroNox NVIS Green A` a partir do perfil ativo selecionado pelo usuário ou de `default`, preservando fonte, cursor, rolagem, opções de execução e recursos não cromáticos.
- Substituir **somente** os atributos associados a cores: `use_theme_colors`, `foreground_color`, `background_color`, `palette`, `cursor_color` se suportado, `background_type = solid` e configurações de cor necessárias.
- `palette` é string com 16 hexadecimais separados por `:`.
- **Nunca modificar a seção `[[default]]`**, `keybindings`, `layouts`, `plugins` ou seções não reconhecidas.
- Se um perfil com nome AeroNox existir mas **não for registrado como recurso gerenciado**, não sobrescrever; oferecer nome alternativo ou interromper.
- Testar preservação de seções desconhecidas e round-trip; formatadores podem mudar a formatação do arquivo, então guardar backup integral, permitir dry-run e preferir alterações mínimas.
- O Terminator pode precisar de reinício ou de janela nova para refletir perfis instalados; documentar isso.

### 6.2 htop

- Config padrão: `${XDG_CONFIG_HOME:-~/.config}/htop/htoprc`; detectar legado `~/.htoprc` quando pertinente.
- Criar uma cópia **gerenciada**, por paleta, do arquivo do usuário (ou defaults construídos/testados), preservando colunas, meters, sorting etc.
- Usar variável `HTOPRC` para iniciar cada cópia, em vez de sobrescrever a config original.
- Priorizar o esquema monocromático nativo/fallback `htop -C` quando necessário; **não prometer RGB ou coloração exata do mockup**. A interface `ncurses` limita a liberdade cromática.
- Testar se o esquema adotado mantém os principais controles legíveis no Terminator vermelho e verde.
- Documentar que htop pode regravar seu próprio `htoprc` no encerramento; backups e snapshots devem refletir esse comportamento.

### 6.3 Vim

- Gerar `~/.vim/colors/aeronox_red.vim` e `~/.vim/colors/aeronox_green.vim` OU alternativa XDG/runtime que funcione em Vim tradicional.
- Criar grupos principais: `Normal`, `Comment`, `Constant`, `String`, `Identifier`, `Statement`, `PreProc`, `Type`, `Special`, `LineNr`, `CursorLine`, `Visual`, `StatusLine`, `Search`, `ErrorMsg`, `WarningMsg`, `DiffAdd`, `DiffDelete`.
- Oferecer `guifg/guibg` para True Color e fallback `ctermfg/ctermbg` (256 cores) coerente.
- Não substituir `.vimrc`; wrapper de inicialização escolhe o `colorscheme`.
- Testar `vim -Nu NONE -n -es` em modo headless quando aplicável, usando runtimepath adequado e verificando ausência de erro no carregamento.
- Documentar que plugins podem sobrescrever `highlight` posteriormente e que paleta não substitui canais semânticos para identificar falhas.

### 6.4 Visual Studio Code

**No MVP, integração assistida e honestamente limitada:**

- Gerar assets de tema para Aviation Red e NVIS Green A em `assets/vscode/` e instruções de importação/aplicação em perfis dedicados (sem modificar o perfil Default).
- Cobrir `workbench.colorCustomizations`, `editor.tokenColorCustomizations`, `editor.semanticTokenColorCustomizations` e as 16 cores `terminal.ansi*`.
- Fornecer um JSONC/snippet de referência para mesclagem manual, sem sobrescrever `settings.json` inteiro.
- Para instalação automática futura, preferir uma **extensão de temas** (`package.json` `contributes.themes` + arquivos de tema) em vez de editar diretamente IDs de perfis e JSONC internos.
- `code --profile <nome>` **seleciona** o perfil, mas não assegura que o tema esteja instalado/aplicado. A CLI deve detectar e informar essa diferença.
- Nunca assumir que as instalações Stable, Insiders, VSCodium, Snap e Flatpak usam os mesmos caminhos; oferecer detectores por edição.
- Mudança de tema do VS Code aberto é implementação opcional posterior, com opt-in claro e documentação do ciclo de restauração.

## 7. Persistência, segurança e backup

### Diretórios

```text
$XDG_CONFIG_HOME/aeronox/config.json         # preferências não sensíveis
$XDG_STATE_HOME/aeronox/state.json           # modo atual e manifest
$XDG_STATE_HOME/aeronox/backups/<timestamp>/ # snapshots locais
$XDG_DATA_HOME/aeronox/                    # recursos gerados gerenciados
```

Defaults: `~/.config`, `~/.local/state`, `~/.local/share`.

### Regras

1. Executar **snapshot antes da primeira mutação** de cada arquivo de usuário; guardar caminho original, hash, tamanho, permissões e horário.
2. Backups com permissões restritivas (`0700` para diretórios; preservar permissões relevantes dos arquivos). Não versionar backups no Git.
3. Escrever em arquivo temporário no mesmo diretório, `fsync` quando viável e `os.replace` para atualização atômica; preservar permissões e proprietário quando aplicável.
4. Não atravessar symlinks inesperados nem escrever fora de `$HOME` sem permissão explícita; recusar caminhos suspeitos, usar whitelist de destinos.
5. Registrar no manifest hashes dos recursos gerenciados. Se alterados pelo usuário, **não sobrescrever nem apagar silenciosamente**; reportar conflito e oferecer resolução explícita.
6. Se uma operação parcialmente concluída falhar, realizar rollback dos arquivos já modificados ou deixar plano de recuperação preciso; testar simulação de falhas.
7. `restore` nunca deve substituir configurações modificadas desde o backup de forma automática. Preferir restaurar apenas o estado `original`; usar operação adicional `backup restore <id>` somente após confirmação e verificação de hash.
8. Idempotência: `install` repetido não deve duplicar seções do Terminator nem sobrescrever mudanças alheias.
9. Redigir logs sem conteúdo integral das configurações (podem conter comandos privados). Sem telemetria ou envio de arquivos à nuvem.
10. Não fazer operações como root, downloads remotos ou `curl | sh`.

## 8. Estrutura de repositório proposta

```text
aeronox/
├── AGENTS.md
├── SPEC.md
├── README.md
├── LICENSE
├── CHANGELOG.md
├── CONTRIBUTING.md
├── pyproject.toml
├── .gitignore
├── .github/
│   └── workflows/
│       └── ci.yml
├── palettes/
│   ├── aviation-red.json
│   └── nvis-green-a.json
├── src/
│   └── aeronox/
│       ├── __init__.py
│       ├── cli.py
│       ├── models.py
│       ├── catalog.py
│       ├── paths.py
│       ├── planning.py
│       ├── storage.py
│       ├── backups.py
│       ├── commands.py
│       └── adapters/
│           ├── base.py
│           ├── terminator.py
│           ├── htop.py
│           ├── vim.py
│           └── vscode.py
├── assets/
│   └── vscode/
├── docs/
│   ├── architecture.md
│   ├── safety-and-restore.md
│   ├── apps.md
│   └── screenshots/
└── tests/
    ├── fixtures/
    │   ├── terminator/
    │   ├── htop/
    │   └── vim/
    ├── test_palettes.py
    ├── test_terminator.py
    ├── test_htop.py
    ├── test_vim.py
    ├── test_backup_restore.py
    └── test_cli.py
```

`AGENTS.md` será conciso e fará referência a este documento. O código-fonte do projeto deve ser em inglês; documentação e mensagens do CLI podem começar em inglês com plano para localização PT-BR.

## 9. Critérios de aceite (Definition of Done)

- [ ] `aeronox --help` e `aeronox doctor` funcionam sem `sudo`.
- [ ] Paletas carregam, têm todos os campos e exatamente 16 entradas ANSI válidas.
- [ ] `aeronox install --dry-run` não modifica nenhum arquivo e lista ações de forma compreensível.
- [ ] Instalação real preserva **byte a byte** a seção `default` e o conteúdo semântico de perfis pessoais, atalhos e layouts; se o arquivo for reformatado, existe backup fiel e diferença previsível.
- [ ] Terminator inclui dois perfis AeroNox selecionáveis por `-p`; nenhum perfil pessoal é apagado.
- [ ] `aeronox open htop` usa config própria e não modifica o `htoprc` original.
- [ ] Os dois esquemas Vim carregam e não requerem modificar `.vimrc`.
- [ ] VS Code recebe artefatos/documentação válidos e perfil de usuário original não é alterado; CLI não promete instalação automática de tema inexistente.
- [ ] `aeronox apply aviation-red` e `apply nvis-green-a` persistem estado e afetam **novas instâncias lançadas via `aeronox open`**.
- [ ] `aeronox restore` volta para original sem excluir perfis ou arquivos do usuário.
- [ ] `aeronox uninstall` remove só os recursos ainda intactos do AeroNox; reporta divergências.
- [ ] Reinstalação é idempotente e segundo `install` não causa duplicações.
- [ ] Testes abrangem XDG customizado, arquivo inexistente, comentários, seções desconhecidas, symlinks, permissões, falha intermediária, alterações concorrentes e paths com espaços.
- [ ] Todos os testes de escrita operam **somente em diretórios temporários**; nunca usam o `$HOME` real na CI.
- [ ] `ruff check .` e `pytest` passam no CI do Ubuntu.
- [ ] README contém instalação, uso, prévia de temas, limitações, retorno ao original, segurança e avisos NVIS.

## 10. Cenários de teste de ponta a ponta

1. **Usuário novo:** sem configurações prévias; gerar perfis sem destruir defaults nem criar `~/.vimrc` desnecessário.
2. **Usuário avançado:** Terminator com perfis, layouts e plugins; duplicar base sem modificar originais.
3. **Reexecução:** duas instalações seguidas; verificar ausência de duplicação e estado consistente.
4. **Mudança pessoal após instalar:** usuário edita um perfil AeroNox; `uninstall` deve detectar conflito e não apagar.
5. **Interrupção:** simular falha após atualizar um arquivo; rollback ou recuperação explícita.
6. **XDG customizado:** instalar com diretórios em um HOME temporário, contendo espaços.
7. **Apps ausentes:** instalar apenas os disponíveis e reportar os restantes como ignorados/pendentes.
8. **Vim sem True Color:** esquema visual aproximado com `cterm*` sem erro.
9. **Retorno ao original:** `apply red` → `apply green` → `restore` → `uninstall`; arquivos pessoais intactos.
10. **VS Code sem perfil preparado:** `aeronox open code` avisa ausência de configuração e não altera `Default`.

## 11. Etapas de implementação para o Codex

Entregar mudanças pequenas, revisáveis e testadas. Ordem sugerida:

- **PR 1 — Fundação:** `pyproject.toml`, CLI, modelos, path resolution XDG, schemas/paletas, testes, README inicial e CI.
- **PR 2 — Segurança:** plano `--dry-run`, manifest, hashes, backups, escrita atômica, rollback e testes adversariais.
- **PR 3 — Terminator:** parser, geração de perfis, detector, start wrapper, testes com fixtures complexas.
- **PR 4 — htop + Vim:** configs separadas, gerador de colorschemes e wrappers com testes.
- **PR 5 — VS Code assistido:** snippets e instruções de perfis; detecção de instalações comuns, limitações explicitadas.
- **PR 6 — Integração:** `apply`, `restore`, `uninstall`, documentação e E2E, capturas reais.

Se implementado em uma única sessão, seguir essa sequência internamente, rodar os testes a cada etapa e registrar pendências. **Não alegar que recursos não implementados já existem.**

## 12. Não objetivos e limites conhecidos

- Não garantir um único comando capaz de recolorir toda janela já aberta.
- Não substituir temas do sistema GNOME/KDE no MVP.
- Não prometer que htop suporte as 16 cores RGB por elemento.
- Não alterar automaticamente `settings.json` do VS Code, `.vimrc`, `.bashrc` ou `.zshrc` no MVP.
- Não confundir a aparência **NVIS Green A inspired** com conformidade técnica NVIS real.
- Não esconder diferenças de contraste sob alegações de redução de fadiga ocular clinicamente comprovada.

## 13. Documentação de referência para implementação

- Terminator, formato de configuração: https://github.com/gnome-terminator/terminator/blob/master/doc/terminator_config.adoc
- htop, comportamento `HTOPRC`/config: https://github.com/htop-dev/htop/blob/main/htop.1.in
- Vim, colorschemes: https://vimhelp.org/usr_06.txt.html
- Vim, True Color: https://vimhelp.org/term.txt.html
- VS Code, perfis e CLI: https://code.visualstudio.com/docs/configure/profiles
- VS Code, temas/overrides: https://code.visualstudio.com/docs/configure/themes
- Codex, `AGENTS.md`: https://learn.chatgpt.com/docs/agent-configuration/agents-md

## 14. Licenciamento e publicação

- Proposta: **MIT**, se todos os recursos e dependências redistribuídos permitirem; confirmar a escolha antes de publicar. Dependências devem conservar seus avisos/licenças.
- Publicar exemplos de configs **sintéticos**, sem exportar arquivos pessoais reais.
- Adicionar assuntos/tags para GitHub: `linux`, `terminal`, `vim`, `vscode`, `terminator`, `htop`, `theme`, `night-mode`, `python`.
- Incluir CONTRIBUTING, instruções de issue e notas sobre compatibilidade.

---

**Resumo de entrega do MVP:** um gerenciador seguro que instala assets de duas paletas, abre novas instâncias de Terminator/htop/Vim de forma coordenada, oferece integração assistida para VS Code e permite restauração sem perder configurações pessoais.
