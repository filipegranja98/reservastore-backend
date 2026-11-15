# API do MVP — Reserva Store

Base: `http://127.0.0.1:8000/api/` em desenvolvimento. JSON UTF-8. Campos monetários são strings decimais em reais; IDs são inteiros, e `codigo` do pedido é UUID. Nos endpoints privados envie `Authorization: Bearer <access>`. Use HTTPS fora de localhost. Exemplos abaixo não contêm credenciais reais.

## Conta e autenticação

`POST auth/cadastro/`

```json
{"username":"cliente_exemplo","password":"uma-senha-forte-e-exclusiva","email":"cliente@example.test","first_name":"Cliente","telefone":"85999999999","papel":"cliente"}
```

`papel` aceita somente `cliente` ou `lojista`; cliente é o padrão. Lojista cadastrado pode preparar sua loja, mas só aparece no catálogo após ativação administrativa. O cadastro não aceita is_staff, is_superuser, is_active ou papel de administrador. Resposta 201: id, username, papel.

| Operação | Método e caminho | Corpo |
|---|---|---|
| Login | POST `token/` | username, password |
| Renovar | POST `token/refresh/` | refresh |
| Verificar | POST `token/verify/` | token |
| Logout | POST `token/logout/` | refresh_token |
| Minha conta | GET `conta/` | — |
| Atualizar contato | PATCH `conta/` | first_name, email, telefone |
| Trocar senha | POST `conta/senha/` | senha_atual, nova_senha |

Login retorna access e refresh. Renovar retorna um novo par e invalida o refresh anterior. Logout exige access e refresh pertencentes ao mesmo usuário; retorna 205 sem corpo. Após trocar senha, entre novamente em todos os dispositivos. O cliente não pode mudar seu próprio papel ou flags administrativas.

## Loja e catálogo privado do lojista

| Recurso | Métodos/caminho | Campos de escrita |
|---|---|---|
| Loja própria | GET/POST `lojas/`; GET/PUT/PATCH/DELETE `lojas/{id}/` | nome, whatsapp, logo, aberta, cor_primaria, cor_secundaria, meios_pagamento, instrucoes_pagamento |
| Categorias próprias | GET/POST `categorias/`; GET/PUT/PATCH/DELETE `categorias/{id}/` | nome |
| Produtos próprios | GET/POST `produtos/`; GET/PUT/PATCH/DELETE `produtos/{id}/` | nome, categoria, preco, imagem, ativo |
| Áreas de entrega próprias | GET/POST `lojista/areas-entrega/`; GET/PUT/PATCH/DELETE `lojista/areas-entrega/{id}/` | condominio, taxa, ativa, prazo_estimado_minutos |

`dono` e `loja` são definidos pelo servidor. Produto só aceita categoria da própria loja; preço não pode ser negativo. Categoria é única por nome dentro da loja na validação da API. Use multipart/form-data para enviar imagens. Limites de upload padrão Django se aplicam; limites adicionais de imagem/tamanho devem ser definidos com a infraestrutura de produção.

Cada lojista tem uma loja. A resposta privada da loja inclui ativa, assinatura_status, assinatura_valida_ate e mensalidade, que só o administrador pode alterar. Loja com pedidos não pode ser excluída; desative-a administrativamente.

`GET lojas/minha_loja` e `GET lojas/minha_loja_completa` preservam os caminhos anteriores, sem barra final. As ações do router também aceitam a versão com barra final.

`meios_pagamento` é uma lista não vazia sem repetições: `pix`, `dinheiro`, `cartao_na_entrega`, `transferencia`. O padrão inicial é PIX e dinheiro; o lojista deve confirmar sua configuração. As instruções são públicas e destinam-se ao pagamento direto para a loja. Não cadastre senhas, tokens ou credenciais de processadores nesse campo.

Área de entrega representa um condomínio atendido por uma loja. A taxa aceita zero. `prazo_estimado_minutos` é opcional e aceita `null` ou um inteiro de 1 a 32767 (limite técnico do campo); nenhum tempo comercial é predefinido. O valor é uma estimativa da loja e não uma garantia de prazo. O nome do condomínio é comparado por normalização Unicode, caixa e espaços; nomes equivalentes não podem ser duplicados na mesma loja. O cliente seleciona o ID da área divulgado no catálogo. O condomínio do endereço deve corresponder à área selecionada.

## Catálogo público

- GET `catalogo/lojas/`
- GET `catalogo/lojas/{loja}/`
- GET `catalogo/lojas/{loja}/categorias/`
- GET `catalogo/lojas/{loja}/produtos/`
- GET `catalogo/lojas/{loja}/areas-entrega/`

Dispensa login. Lista somente lojas ativas, com assinatura ativa e validade não vencida. Data de validade vazia indica aprovação manual sem vencimento definido. Produtos e áreas inativos não são públicos. Não expõe proprietário, mensalidade ou dados de clientes. O caminho legado `GET lojas/todas_lojas` continua disponível.

## Endereços do cliente

GET/POST `enderecos/`; GET/PUT/PATCH/DELETE `enderecos/{id}/`.

```json
{"condominio":"Reserva","bloco":"A","apartamento":"101","destinatario":"Cliente","telefone":"85999999999","complemento":"Interfone 101"}
```

cliente/usuário é sempre definido pelo token. Não existe compartilhamento de endereços entre clientes. O pedido guarda uma cópia do endereço no checkout.

## Carrinhos por loja

| Método/caminho | Comportamento |
|---|---|
| GET `carrinhos/` | Lista todos os carrinhos do próprio cliente |
| GET `carrinhos/{loja}/` | Carrinho dessa loja; vazio se ainda não houver itens |
| DELETE `carrinhos/{loja}/` | Limpa somente o carrinho dessa loja |
| POST `carrinhos/{loja}/itens/` | Corpo: produto, quantidade; define/substitui a quantidade desse produto |
| PATCH `carrinhos/{loja}/itens/{item}/` | Corpo: quantidade |
| DELETE `carrinhos/{loja}/itens/{item}/` | Remove esse item |

Quantidade: 1–99 por produto; até 100 produtos distintos por carrinho. O ID no caminho é o ID da loja, e o item pertence ao carrinho da pessoa autenticada. Produto de outra loja é rejeitado. Carrinhos de outras lojas não são apagados ao comprar. Subtotal do carrinho reflete preços atuais e não inclui entrega.

## Prévia antes da confirmação

`POST pedidos/previa/` usa loja, endereco, area_entrega, meio_pagamento e observacoes opcionais, com as mesmas permissões e validações do checkout. Não envie chave_checkout, total, preço ou prazo: esses campos são recusados.

```json
{"loja":1,"endereco":1,"area_entrega":1,"meio_pagamento":"pix"}
```

Resposta 200: loja, loja_nome, area_entrega, endereco, meio_pagamento, instrucoes_pagamento, itens, subtotal, taxa_entrega, total e prazo_estimado_minutos. Valores monetários são strings com duas casas. O prazo pode ser null. Itens incluem produto, nome, preco_unitario, quantidade e total. Não cria pedido, eventos ou itens de pedido; não modifica nem limpa carrinhos. Endereço de outro cliente, área de outra loja, produtos indisponíveis e loja suspensa são rejeitados.

A prévia não congela preços, taxas ou prazo. No botão de confirmação, envie o checkout normal: ele volta a validar a compra e registra os valores atuais. O pedido guarda o prazo estimado naquele momento; mudanças posteriores na área não alteram esse registro.

## Checkout e pedidos do cliente

`POST pedidos/`

```json
{"loja":1,"endereco":1,"area_entrega":1,"meio_pagamento":"pix","observacoes":"Chamar no interfone","chave_checkout":"f4318180-c35b-4acc-9b2d-ff31c2bda497"}
```

`chave_checkout` é opcional, mas recomendada: gere um UUID no aplicativo para cada tentativa de compra e reutilize-o se repetir a mesma requisição por falha de conexão. A primeira resposta é 201; repetição da mesma chave pelo mesmo cliente/loja retorna o pedido original com 200 e não consome um novo carrinho. Use uma chave nova para outra compra. Reutilizar a chave em outra loja é rejeitado.

O backend valida loja/assinatura, produtos, área, endereço próprio e meio aceito. Recalcula os preços atuais, subtotal e taxa sem aceitar valores do aplicativo. Itens, preços, taxa, prazo_estimado_minutos, endereço e instruções de pagamento ficam registrados no pedido. Pedidos antigos mantêm prazo null. O carrinho dessa loja só é removido quando a transação termina com sucesso. Falhas preservam o carrinho. Repetição sem chave após sucesso encontra o carrinho removido e não cria outro pedido.

- GET `pedidos/`: pedidos do cliente autenticado.
- GET `pedidos/{id}/`: detalhes, itens, valores, endereço e eventos.
- POST `pedidos/{id}/cancelar/`: corpo vazio; somente enquanto recebido.
- POST `pedidos/{id}/informar-pagamento/`: corpo vazio; marca informado, sem confirmar recebimento.

Não há PUT/PATCH/DELETE de pedido. O cliente não informa preço, total, cliente, status ou confirmação de pagamento. Dados de outros clientes retornam 404.

## Painel do lojista

- GET `lojista/pedidos/` (opcional: `?status=recebido`).
- GET `lojista/pedidos/{id}/`.
- POST `lojista/pedidos/{id}/transicao/`: `{"status":"aceito"}`.
- POST `lojista/pedidos/{id}/pagamento/`: `{"status":"confirmado"}` ou `{"status":"estornado"}`.

| Estado atual | Próximos estados permitidos ao lojista |
|---|---|
| recebido | aceito, cancelado |
| aceito | preparando, cancelado |
| preparando | saiu_entrega, cancelado |
| saiu_entrega | entregue |
| entregue/cancelado | Nenhum |

Pagamento começa pendente. O cliente pode registrar informado; o lojista pode confirmar pendente/informado e depois registrar estornado. Pedido cancelado não aceita nova confirmação de pagamento. Cancelar um pedido confirmado não realiza estorno automático nem muda seu pagamento. Estorno é apenas registro do acerto realizado diretamente pelo lojista. Cada transição gera evento com autor e horário. Entrega própria da loja, sem logística compartilhada.

## Administração da plataforma

Somente contas staff/superuser, atribuídas fora do cadastro público. Administrador não se torna cliente ou lojista automaticamente.

- GET `administracao/lojas/` e GET `administracao/lojas/{id}/`.
- PUT/PATCH `administracao/lojas/{id}/`: ativa, assinatura_status, assinatura_valida_ate, mensalidade.
- GET `administracao/usuarios/` e GET `administracao/usuarios/{id}/` (leitura).
- GET `administracao/pedidos/` e GET `administracao/pedidos/{id}/` (leitura).
- `/admin/`: administração Django de contas e demais registros; pedidos/eventos ficam protegidos contra criação/remoção manual.

```json
{"ativa":true,"assinatura_status":"ativa","assinatura_valida_ate":null,"mensalidade":null}
```

Status de assinatura: pendente, ativa, suspensa, cancelada. Mensalidade é opcional e não negativa, sem preço predefinido. Esta configuração pertence somente à loja/lojista e não cria cobrança. Suspensão, vencimento ou desativação bloqueiam catálogo/novas compras; pedidos já recebidos continuam acessíveis para serem concluídos.

## Respostas e integração futura

401: credenciais ausentes/inválidas. 403: papel sem permissão. 404: recurso inexistente ou fora do escopo da pessoa. 400: validação/regra de negócio. 405: operação não permitida. 429: limite de tentativas, com Retry-After.

### Paginação opcional

Envie `page` e/ou `page_size` nos GETs de listagem para optar pelo envelope paginado. `page` começa em 1; o tamanho padrão é 20 e page_size deve estar entre 1 e 100. Tamanho inválido retorna 400; página inválida/inexistente retorna 404. Uma lista vazia na primeira página retorna count 0 e results [].

```json
{"count":0,"next":null,"previous":null,"results":[]}
```

O exemplo acima representa uma lista vazia; quando há registros, results contém os dados da página e next/previous indicam as URLs de navegação. count e as páginas são calculados depois de aplicar as permissões da pessoa autenticada. Siga next/previous preservando o token quando necessário. A navegação anterior mantém `page=1`, para não trocar de formato ao voltar à primeira página.

Suportado em: catalogo/lojas e suas ações produtos/categorias/areas-entrega; lojas/produtos/categorias privados; enderecos; lojista/areas-entrega; pedidos; lojista/pedidos; administracao/lojas, administracao/pedidos e administracao/usuarios. As respostas sem parâmetros continuam sendo arrays. Carrinhos, endpoints legados todas_lojas/minha_loja_completa, detalhes e ações POST não são paginados.

O aplicativo novo deve sempre solicitar paginação nas listagens suportadas. As respostas completas sem paginação permanecem apenas para compatibilidade. Não há cálculo de estoque ou reserva de unidades. Integração financeira futura deverá ser um módulo separado do estado do pedido; nenhum processador ou cobrança automática foi implementado.


## Identidade visual da loja

As respostas públicas e privadas de loja incluem `cor_primaria` e `cor_secundaria`. Aceitam apenas `#RRGGBB` (letras maiúsculas ou minúsculas); os padrões são `#17624E` e `#EAF1E9`. O lojista pode atualizar as cores somente da própria loja, com as mesmas permissões do recurso; o cliente não administra lojas. O responsável também pode editar logo/cores na seção **Identidade visual** do Django Admin.

O campo `logo` mantém o contrato de upload de imagem existente (multipart/form-data). A migração `lojas/0004` acrescenta as cores e preserva os logos, produtos e vínculos existentes. Sirva as URLs de mídia por storage/servidor apropriado em produção; não use o servidor de desenvolvimento para isso.


## Estado operacional: aberta/fechada

`aberta` é um booleano público/privado da loja, editável pelo proprietário nas rotas privadas e pelo responsável no Django Admin. Padrão `false`. A migração `lojas/0005` inicia lojas existentes fechadas sem alterar aprovação, assinatura, carrinhos ou pedidos. Marque explicitamente para iniciar atendimento.

O catálogo continua incluindo lojas aprovadas fechadas; não use `ativa` para representar horário de operação. Adicionar/ajustar itens, prévia e novo checkout retornam 400 quando a loja está fechada. Consulta de catálogo/carrinho, remoção de itens e processamento de pedidos existentes permanecem disponíveis. Repetição idempotente de um pedido já criado retorna o pedido original mesmo após fechar a loja e não consome outro carrinho. Não há agenda/horários automáticos nesta etapa.


## Tipos de loja e filtros de categorias

- `GET catalogo/tipos-loja/?page=1&page_size=20`: cadastro global, somente leitura pela API. Administração cria tipos no Django Admin. Campos: id e nome.
- `GET catalogo/lojas/?tipo_loja={id}&page=1&page_size=20`: filtro de tipo antes da paginação. A loja inclui `tipo_loja` e `tipo_loja_nome`, nulos quando ainda não classificada.
- `GET catalogo/lojas/{loja}/produtos/?categoria={id}&page=1&page_size=20`: filtro pela categoria da própria loja antes da paginação. Categoria alheia retorna 404; identificador inválido retorna 400.
- O proprietário escolhe um tipo existente com `PATCH lojas/{id}/` e `{"tipo_loja": id}` ou null. A propriedade continua sendo validada pelo servidor.
- `POST categorias/` com `{"nome":"Bebidas"}` já cria a categoria na loja do proprietário autenticado. Não envie outro dono/loja. Use `PATCH produtos/{id}/` com `{"categoria": id}` para organizar apenas seus produtos. Categorias e produtos alheios não são acessíveis.

Tipos globais são separados das categorias dos produtos. A migração `lojas/0006` preserva lojas/produtos/categorias e adiciona uma classificação opcional. Excluir um tipo vinculado é protegido. O app mantém cadastro público só de cliente, com painel de categorias disponível a contas de lojista existentes.


## Contato público da loja

A loja pública/privada inclui `email_contato`, separado do email privado da conta proprietária. Pode ser o email da loja ou do dono, informado explicitamente. O campo `whatsapp` existente continua representando o telefone próprio da loja. Ambos podem ser atualizados pelo proprietário nas rotas privadas existentes. Valores de email enviados são validados; registros antigos sem email são preservados.

No formulário de Loja do Django Admin, nome, conta proprietária, email de contato e telefone são obrigatórios. O telefone administrativo deve conter DDD e 10–15 dígitos. Não foi criado outro campo de telefone nem exposto automaticamente o email da conta. Migração `lojas/0007` adiciona email_contato com valor vazio nas lojas existentes e altera apenas a apresentação do telefone no modelo.
