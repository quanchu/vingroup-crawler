class CrawlerError(Exception):
    """A user-actionable crawl or extraction failure."""


class AnalysisError(Exception):
    """An OpenAI or semantic-validation failure."""

