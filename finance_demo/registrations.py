from finance_demo.agents import BriefingAgent, EnrichmentAgent
from finance_demo.dataset import dataset_summary, search_signals, upsert_signals
from finance_demo.reddit import RedditFinanceSource
from flow import registry

registry.register_source("reddit.finance", RedditFinanceSource())
registry.register_agent("finance.enrich-post", EnrichmentAgent())
registry.register_agent("finance.grounded-brief", BriefingAgent())
registry.register_function("dataset.upsert-signals", upsert_signals)
registry.register_function("dataset.summary", dataset_summary)
registry.register_function("dataset.search-signals", search_signals)
