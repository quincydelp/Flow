from finance_demo.agents import BriefingAgent, EnrichmentAgent
from finance_demo.dataset import (
    build_sentiment_indices,
    dataset_summary,
    list_sentiment_indices,
    merge_records,
    search_signals,
    upsert_signals,
)
from finance_demo.gdelt import GdeltFinanceSource
from finance_demo.hackernews import HackerNewsFinanceSource
from flow import registry

registry.register_source("hackernews.finance", HackerNewsFinanceSource())
registry.register_source("gdelt.finance-news", GdeltFinanceSource())
registry.register_agent("finance.enrich-post", EnrichmentAgent())
registry.register_agent("finance.grounded-brief", BriefingAgent())
registry.register_function("dataset.upsert-signals", upsert_signals)
registry.register_function("dataset.merge-records", merge_records)
registry.register_function("dataset.build-sentiment-indices", build_sentiment_indices)
registry.register_function("dataset.list-sentiment-indices", list_sentiment_indices)
registry.register_function("dataset.summary", dataset_summary)
registry.register_function("dataset.search-signals", search_signals)
