import os
import re
import requests
import urllib.parse
from bs4 import BeautifulSoup
from typing import List, Dict, Any, Tuple
from pydantic import BaseModel, Field
from google import genai
from google.genai import types

from .harness import call_harness_agent

# Define Pydantic models for structured Gemini responses
class ExtractedNode(BaseModel):
    id: str = Field(
        description="A unique snake_case or camelCase identifier for the node based on its name (e.g., graph_rag, agent_as_a_graph, wrrf_algorithm, mcp_protocol)."
    )
    type: str = Field(
        description="Must be exactly one of: 'agent', 'skill', 'tool', 'best_practice', 'theoretical_knowledge', 'concept'"
    )
    name: str = Field(
        description="Clean, concise, and professional human-readable name of the entity."
    )
    description: str = Field(
        description="A comprehensive description of what this entity does, its capabilities, or theoretical details extracted from the text."
    )

class ExtractedEdge(BaseModel):
    source_id: str = Field(description="The unique identifier (id) of the source node.")
    target_id: str = Field(description="The unique identifier (id) of the target node.")
    relation_type: str = Field(
        description="Capitalized relationship type. Must be exactly one of: 'HAS_SKILL', 'HAS_TOOL', 'REQUIRES_TOOL', 'BASED_ON', 'REFERENCES', 'MENTIONS', 'IS_A'"
    )
    description: str = Field(
        description="A brief description of why these two entities are connected in the context of agent multi-agent systems."
    )

class ExtractedGraph(BaseModel):
    nodes: List[ExtractedNode] = Field(description="List of all unique nodes extracted from the text.")
    edges: List[ExtractedEdge] = Field(description="List of all unique relationships connecting the extracted nodes.")


class KnowledgeExtractor:
    def __init__(self):
        self.api_key = os.environ.get("GEMINI_API_KEY")
        if self.api_key:
            self.client = genai.Client(api_key=self.api_key)
        else:
            self.client = None

    def fetch_url_content(self, url: str) -> Tuple[str, str]:
        """
        Crawls a URL, strips HTML tags, and returns the page Title and clean body text.
        """
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        try:
            response = requests.get(url, headers=headers, timeout=15)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, "html.parser")
            
            # Remove script and style elements
            for script in soup(["script", "style", "meta", "noscript", "header", "footer", "nav"]):
                script.decompose()
                
            title = soup.title.string.strip() if soup.title else "Scraped Document"
            text = soup.get_text(separator="\n")
            
            # Clean up white space
            lines = (line.strip() for line in text.splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            clean_text = "\n".join(chunk for chunk in chunks if chunk)
            
            return title, clean_text
        except Exception as e:
            print(f"Error fetching URL content: {e}")
            parsed = urllib.parse.urlparse(url)
            title = parsed.netloc + parsed.path
            return title, f"Failed to fetch content from URL: {url}. Error: {str(e)}"

    def extract_graph_from_text(self, text: str, source_title: str) -> ExtractedGraph:
        """
        Extracts entities and relationships mapped to our Agent Knowledge Graph schema.
        Prioritizes the Antigravity 2.0 IDE agent harness (agentapi), falling back
        to direct Gemini Structured APIs or a local deterministic builder.
        """
        prompt = f"""
        Analyze the following text describing software agents, tools, skills, best practices, theories, or software design principles.
        Extract all major concepts, skills, tools, agents, theoretical models, and best practices.
        
        CRITICAL CONSTRAINT: You MUST represent ONLY the pure information and conceptual knowledge in itself. Do NOT extract or create any nodes or relationships representing the source document, page title, URL, website origin, web page itself, or scraping metadata (for example, do NOT create nodes for the website, repo, or document, and do NOT create 'REFERENCES' or 'MENTIONS' edges pointing to a source document). Extract ONLY the pure domain concepts, tools, skills, or practices explained within the text.
        
        You MUST return ONLY a valid, parseable JSON object matching this schema structure, without any conversational preamble or trailing remarks:
        {{
          "nodes": [
            {{
              "id": "unique_snake_case_slug_1",
              "type": "one of: 'agent', 'skill', 'tool', 'best_practice', 'theoretical_knowledge', 'concept'",
              "name": "Human Readable Name",
              "description": "Comprehensive explanation of capabilities/properties"
            }}
          ],
          "edges": [
            {{
              "source_id": "source_node_id",
              "target_id": "target_node_id",
              "relation_type": "one of: 'HAS_SKILL', 'HAS_TOOL', 'REQUIRES_TOOL', 'BASED_ON', 'REFERENCES', 'MENTIONS', 'IS_A'",
              "description": "Brief explanation of structural connection context"
            }}
          ]
        }}
        
        Text Content to Analyze:
        ---
        {text[:4000]}
        ---
        """
        
        # 1. Attempt Ingestion via Antigravity 2.0 IDE Harness
        print("[Extractor] Attempting entity extraction via IDE Harness (agentapi)...")
        harness_response = call_harness_agent(prompt)
        
        if harness_response:
            try:
                cleaned_json = self._clean_json_blocks(harness_response)
                parsed_graph = ExtractedGraph.model_validate_json(cleaned_json)
                print("[Extractor] Successfully completed extraction using IDE Harness.")
                return parsed_graph
            except Exception as harness_err:
                print(f"[Extractor] Harness JSON extraction failed or was malformed: {harness_err}.")
 
        # 2. Fallback to Direct Gemini API call
        if self.client:
            print("[Extractor] Falling back to direct Gemini 2.5 API with Structured Schema...")
            try:
                response = self.client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=ExtractedGraph,
                        temperature=0.1
                    )
                )
                return ExtractedGraph.model_validate_json(response.text)
            except Exception as e:
                print(f"[Extractor] Direct Gemini API structured call failed: {e}.")
 
        # 3. Double-fallback to Local Deterministic builder
        print("[Extractor] Falling back to local offline deterministic model extraction.")
        return self._generate_fallback_graph(text, source_title)
 
    def _clean_json_blocks(self, text: str) -> str:
        """Strips markdown code boundaries (e.g. ```json ... ```) from JSON envelopes."""
        cleaned = text.strip()
        
        # Remove ```json ... ``` blocks if present
        json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, re.DOTALL)
        if json_match:
            return json_match.group(1).strip()
            
        # Strip simple ``` block wrappers
        cleaned = re.sub(r"^```(?:json)?", "", cleaned)
        cleaned = re.sub(r"```$", "", cleaned)
        return cleaned.strip()
 
    def _generate_fallback_graph(self, text: str, source_title: str) -> ExtractedGraph:
        """
        A high-quality fallback parser that uses pattern matching or structured dummy data
        to mock graph extraction if no API/harness is reachable.
        Only extracts conceptual elements and relationship structures, keeping metadata strictly isolated.
        """
        nodes = []
        edges = []
        
        keywords = {
            "clean_code": ("best_practice", "Clean Code", "Writing readable, simple, and maintainable software according to team engineering standards."),
            "solid": ("theoretical_knowledge", "SOLID Principles", "Five design principles (Single Responsibility, Open/Closed, Liskov Substitution, Interface Segregation, Dependency Inversion) to make software designs understandable, flexible, and maintainable."),
            "factory": ("tool", "Factory Pattern", "A creational design pattern that provides an interface for creating objects in a superclass, but allows subclasses to alter the type of objects that will be created."),
            "adapter": ("tool", "Adapter Pattern", "A structural design pattern that allows objects with incompatible interfaces to collaborate."),
            "strategy": ("tool", "Strategy Pattern", "A behavioral design pattern that lets you define a family of algorithms, put each of them into a separate class, and make their objects interchangeable."),
            "command": ("tool", "Command Pattern", "A behavioral design pattern that turns a request into a stand-alone object that contains all information about the request."),
            "testing": ("best_practice", "Unit Testing", "The practice of testing individual units of source code to determine whether they are fit for use, highly emphasized in professional software engineering."),
            "design_patterns": ("theoretical_knowledge", "Design Patterns", "Reused, proven paradigms and solutions to common problems in software design.")
        }
        
        # Check standard keywords
        for kw, (ntype, name, desc) in keywords.items():
            if kw in text.lower():
                node_id = f"concept_{kw}"
                nodes.append(ExtractedNode(id=node_id, type=ntype, name=name, description=desc))
        
        # Connect patterns to their parent categories or related structures
        has_patterns = False
        for node in nodes:
            if node.id in ["concept_factory", "concept_adapter", "concept_strategy", "concept_command"]:
                has_patterns = True
                
        # If we have Design Patterns and sub-patterns, link them
        if "concept_design_patterns" in [n.id for n in nodes] and has_patterns:
            for node in nodes:
                if node.id in ["concept_factory", "concept_adapter", "concept_strategy", "concept_command"]:
                    edges.append(ExtractedEdge(
                        source_id=node.id,
                        target_id="concept_design_patterns",
                        relation_type="IS_A",
                        description=f"The {node.name} is a design pattern under software design."
                    ))
                    
        # Link clean code and design patterns to SOLID principles if present
        if "concept_solid" in [n.id for n in nodes]:
            if "concept_clean_code" in [n.id for n in nodes]:
                edges.append(ExtractedEdge(
                    source_id="concept_clean_code",
                    target_id="concept_solid",
                    relation_type="BASED_ON",
                    description="Clean code practice is built upon the SOLID software design principles."
                ))
            if "concept_design_patterns" in [n.id for n in nodes]:
                edges.append(ExtractedEdge(
                    source_id="concept_design_patterns",
                    target_id="concept_solid",
                    relation_type="BASED_ON",
                    description="Design patterns leverage class design rules matching SOLID principles."
                ))
                
        # Default safety fallback if nothing matches
        if not nodes:
            nodes.append(ExtractedNode(
                id="concept_software_design",
                type="theoretical_knowledge",
                name="Software Design Principles",
                description="Principles, patterns, and best practices for creating clean, maintainable, and decoupled software systems."
            ))
            
        return ExtractedGraph(nodes=nodes, edges=edges)

    @staticmethod
    def chunk_text(text: str, chunk_size: int = 600, overlap: int = 150) -> List[str]:
        """Splits clean body text into smaller, overlapping chunks suitable for semantic vector indexing."""
        chunks = []
        words = text.split()
        if not words:
            return []
            
        i = 0
        while i < len(words):
            chunk_words = words[i:i + chunk_size]
            chunk_text = " ".join(chunk_words)
            chunks.append(chunk_text)
            i += (chunk_size - overlap)
            
        return chunks
