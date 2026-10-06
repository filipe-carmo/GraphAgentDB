"""Turns raw text or a web page into an `ExtractedGraph` of concepts and relations."""

import logging
import urllib.parse

import requests
from bs4 import BeautifulSoup

from .llm import LLMClient
from .models import ExtractedEdge, ExtractedGraph, ExtractedNode

logger = logging.getLogger(__name__)

# Very long pages are cut to keep extraction cost bounded; the cut is logged.
MAX_EXTRACTION_CHARS = 200_000

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

EXTRACTION_PROMPT = """
Build a knowledge graph from the text below, which describes software agents, tools, skills,
best practices, theories or software design principles.

Nodes are the major concepts in the text. Give each a unique snake_case id and one type:
agent, skill, tool, best_practice, theoretical_knowledge or concept. Edges connect two of
those node ids with one relation type: HAS_SKILL, HAS_TOOL, REQUIRES_TOOL, BASED_ON,
REFERENCES, MENTIONS or IS_A.

Capture the domain knowledge only. The graph is reused across many sources, so nodes or
edges about the source itself (its title, URL, website or page) would be noise.

<text>
{text}
</text>
"""

# Offline keyword extractor, used when no LLM is reachable: keyword -> (type, name, description).
FALLBACK_CONCEPTS = {
    "clean_code": (
        "best_practice",
        "Clean Code",
        "Writing readable, simple, and maintainable software according to team engineering standards.",
    ),
    "solid": (
        "theoretical_knowledge",
        "SOLID Principles",
        "Five design principles (Single Responsibility, Open/Closed, Liskov Substitution, Interface "
        "Segregation, Dependency Inversion) to make software designs understandable, flexible, and "
        "maintainable.",
    ),
    "factory": (
        "tool",
        "Factory Pattern",
        "A creational design pattern that provides an interface for creating objects in a superclass, "
        "but allows subclasses to alter the type of objects that will be created.",
    ),
    "adapter": (
        "tool",
        "Adapter Pattern",
        "A structural design pattern that allows objects with incompatible interfaces to collaborate.",
    ),
    "strategy": (
        "tool",
        "Strategy Pattern",
        "A behavioral design pattern that lets you define a family of algorithms, put each of them "
        "into a separate class, and make their objects interchangeable.",
    ),
    "command": (
        "tool",
        "Command Pattern",
        "A behavioral design pattern that turns a request into a stand-alone object that contains all "
        "information about the request.",
    ),
    "testing": (
        "best_practice",
        "Unit Testing",
        "The practice of testing individual units of source code to determine whether they are fit "
        "for use.",
    ),
    "design_patterns": (
        "theoretical_knowledge",
        "Design Patterns",
        "Reused, proven paradigms and solutions to common problems in software design.",
    ),
}

PATTERN_IDS = {"concept_factory", "concept_adapter", "concept_strategy", "concept_command"}


def fetch_url_content(url: str, timeout: int = 15) -> tuple[str, str]:
    """Downloads a page and returns (title, visible body text)."""
    try:
        response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
        response.raise_for_status()
    except requests.RequestException as exc:
        logger.warning("Failed to fetch %s: %s", url, exc)
        parsed = urllib.parse.urlparse(url)
        return parsed.netloc + parsed.path, ""

    soup = BeautifulSoup(response.text, "html.parser")
    for tag in soup(["script", "style", "meta", "noscript", "header", "footer", "nav"]):
        tag.decompose()
    title = soup.title.string.strip() if soup.title and soup.title.string else "Scraped Document"

    lines = (line.strip() for line in (soup.body or soup).get_text(separator="\n").splitlines())
    phrases = (phrase.strip() for line in lines for phrase in line.split("  "))
    return title, "\n".join(p for p in phrases if p)


def fallback_graph(text: str) -> ExtractedGraph:
    """Keyword-based extraction so the pipeline still works without any LLM."""
    lowered = text.lower()
    nodes = [
        ExtractedNode(id=f"concept_{kw}", type=ntype, name=name, description=desc)
        for kw, (ntype, name, desc) in FALLBACK_CONCEPTS.items()
        if kw in lowered
    ]
    ids = {n.id for n in nodes}
    edges: list[ExtractedEdge] = []

    if "concept_design_patterns" in ids:
        edges += [
            ExtractedEdge(
                source_id=n.id,
                target_id="concept_design_patterns",
                relation_type="IS_A",
                description=f"The {n.name} is a design pattern under software design.",
            )
            for n in nodes
            if n.id in PATTERN_IDS
        ]
    if "concept_solid" in ids:
        if "concept_clean_code" in ids:
            edges.append(
                ExtractedEdge(
                    source_id="concept_clean_code",
                    target_id="concept_solid",
                    relation_type="BASED_ON",
                    description="Clean code practice is built upon the SOLID design principles.",
                )
            )
        if "concept_design_patterns" in ids:
            edges.append(
                ExtractedEdge(
                    source_id="concept_design_patterns",
                    target_id="concept_solid",
                    relation_type="BASED_ON",
                    description="Design patterns apply class design rules from SOLID.",
                )
            )

    if not nodes:
        nodes.append(
            ExtractedNode(
                id="concept_software_design",
                type="theoretical_knowledge",
                name="Software Design Principles",
                description="Principles, patterns, and best practices for creating clean, "
                "maintainable, and decoupled software systems.",
            )
        )
    return ExtractedGraph(nodes=nodes, edges=edges)


class KnowledgeExtractor:
    def __init__(self, llm: LLMClient):
        self.llm = llm

    def extract(self, text: str) -> ExtractedGraph:
        if len(text) > MAX_EXTRACTION_CHARS:
            logger.warning(
                "Text has %d characters; extracting from the first %d",
                len(text),
                MAX_EXTRACTION_CHARS,
            )
        prompt = EXTRACTION_PROMPT.format(text=text[:MAX_EXTRACTION_CHARS])
        graph = self.llm.generate_json(prompt, ExtractedGraph)
        if graph is not None:
            return graph
        logger.info("No LLM available, using offline keyword extraction")
        return fallback_graph(text)
