# Resultados preliminares do Checkpoint 3

Este diretório contém resultados reproduzíveis gerados a partir do protótipo containerizado do **task manager**. A execução oficial pode ser refeita na VM do LaSDPC com:

1. `make up`
2. aguardar pelo menos 2 ciclos do serviço `collector`
3. `python3 -m pip install -r experiments/requirements.txt`
4. `make checkpoint3` para dezenas de milhares de requisições ou `WORKLOAD=hundreds make checkpoint3` para centenas de milhares.

Perfis de carga:

| Perfil | Cenários | Requisições-alvo |
|---|---|---:|
| `quick` | `rest_low`, `rest_medium`, `soap_low`, `soap_medium`, `mixed_medium` | teste rápido |
| `tens` | `rest_10k`, `soap_10k`, `mixed_20k` | 10.000 a 20.000 |
| `hundreds` | `rest_100k`, `soap_100k`, `mixed_200k` | 100.000 a 200.000 |

## Evidência inicial versionada

- Domínio: gerenciador de tarefas.
- Amostra registrada em `data/raw/evidence_task_seed.json`.
- Variáveis funcionais: título, descrição, status e prioridade.

## Métricas geradas automaticamente

- Latência média por protocolo.
- Desvio padrão.
- Intervalo de confiança de 95%.
- Percentil 95 de latência.
- Throughput efetivo em requisições/s.
- Tamanho médio do payload enviado.
- Pontuação de esforço de manutenção da interface.
- Taxa de sucesso.

O throughput é calculado como vazão efetiva média por repetição. O tamanho de payload considera o corpo enviado na requisição, incluindo o envelope XML no caso SOAP. A pontuação de manutenção da interface é um proxy reprodutível: operações públicas + campos funcionais + artefatos de contrato/interface. Com o domínio atual, REST soma 13 pontos e SOAP soma 15 pontos.

Os arquivos finais são gravados em `results/raw/experiment_latency.csv`, `results/tables/summary_metrics.csv`, `results/figures/latency_ci95.png`, `results/figures/success_rate.png` e `results/figures/throughput_payload.png`.

## Interpretação esperada

REST deve apresentar menor latência média por usar JSON/HTTP sem envelope XML. SOAP deve preservar a vantagem de contrato formal via WSDL e permitir discutir o custo de governança e interoperabilidade em um domínio CRUD equivalente.
