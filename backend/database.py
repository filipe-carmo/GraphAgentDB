import os
import shutil
from typing import List, Dict, Any, Optional
import kuzu

DB_FILE = os.path.join(os.path.dirname(__file__), "kuzu_db.db")

# Thread-safe connection cache to prevent in-process database lock errors
_database = None

def get_connection(db_path: str = DB_FILE) -> kuzu.Connection:
    """Returns a connection to the in-process Kuzu Database."""
    global _database
    if _database is None:
        dir_name = os.path.dirname(db_path)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)
        _database = kuzu.Database(db_path)
    return kuzu.Connection(_database)

def init_db(db_path: str = DB_FILE):
    """Initializes Kuzu graph schemas (Node tables and Relationship tables)."""
    conn = get_connection(db_path)
    
    # 1. Check existing tables in Kuzu Graph
    result = conn.execute("CALL show_tables() RETURN name")
    existing_tables = []
    while result.has_next():
        existing_tables.append(result.get_next()[0])

    # 2. Initialize Node Property Table
    if "Node" not in existing_tables:
        print("Creating Kuzu Node Table schema...")
        conn.execute("""
        CREATE NODE TABLE Node (
            id STRING,
            type STRING,
            name STRING,
            description STRING,
            PRIMARY KEY (id)
        )
        """)

    # 3. Initialize Relationships Property Tables
    relationship_types = [
        "HAS_SKILL",
        "HAS_TOOL",
        "REQUIRES_TOOL",
        "BASED_ON",
        "REFERENCES",
        "MENTIONS",
        "IS_A"
    ]
    
    for rel in relationship_types:
        if rel not in existing_tables:
            print(f"Creating Kuzu Relationship Table schema: {rel}...")
            # Kuzu requires FROM and TO tables to be explicitly defined
            conn.execute(f"CREATE REL TABLE {rel} (FROM Node TO Node, description STRING)")

def upsert_node(
    id: str,
    type: str,
    name: str,
    description: Optional[str] = None,
    properties: Optional[Dict[str, Any]] = None, # Left for compatibility, description holds the main info
    db_path: str = DB_FILE
) -> Dict[str, Any]:
    """Inserts a new node or updates an existing one inside Kuzu Node Table."""
    conn = get_connection(db_path)
    description_val = description or ""
    
    # Check if node exists
    check_query = "MATCH (n:Node {id: $id}) RETURN n.id"
    result = conn.execute(check_query, {"id": id})
    
    if result.has_next():
        # Update node
        update_query = """
        MATCH (n:Node {id: $id})
        SET n.type = $type,
            n.name = $name,
            n.description = $description
        """
        conn.execute(update_query, {"id": id, "type": type, "name": name, "description": description_val})
    else:
        # Create node
        create_query = """
        CREATE (n:Node {
            id: $id,
            type: $type,
            name: $name,
            description: $description
        })
        """
        conn.execute(create_query, {"id": id, "type": type, "name": name, "description": description_val})
        
    return {"id": id, "type": type, "name": name, "description": description_val}

def upsert_edge(
    source_id: str,
    target_id: str,
    relation_type: str,
    properties: Optional[Dict[str, Any]] = None,
    db_path: str = DB_FILE
) -> Dict[str, Any]:
    """Inserts a relationship edge in Kuzu between two Node records."""
    conn = get_connection(db_path)
    desc = ""
    if properties and "description" in properties:
        desc = properties["description"]
        
    # Standardize edge relations to matches in Kuzu
    valid_relations = ["HAS_SKILL", "HAS_TOOL", "REQUIRES_TOOL", "BASED_ON", "REFERENCES", "MENTIONS", "IS_A"]
    if relation_type not in valid_relations:
        relation_type = "REFERENCES"
        
    # Check if edge exists to prevent duplicates
    check_query = f"MATCH (a:Node {{id: $src}})-[r:{relation_type}]->(b:Node {{id: $tgt}}) RETURN r"
    result = conn.execute(check_query, {"src": source_id, "tgt": target_id})
    
    if not result.has_next():
        # 1. Create relation
        create_query = f"MATCH (a:Node), (b:Node) WHERE a.id = $src AND b.id = $tgt CREATE (a)-[r:{relation_type}]->(b)"
        conn.execute(create_query, {"src": source_id, "tgt": target_id})
        # 2. Set description property
        if desc:
            desc_escaped = desc.replace("'", "\\'")
            set_query = f"MATCH (a:Node)-[r:{relation_type}]->(b:Node) WHERE a.id = $src AND b.id = $tgt SET r.description = '{desc_escaped}'"
            conn.execute(set_query, {"src": source_id, "tgt": target_id})
        
    return {
        "id": f"{source_id}_{relation_type}_{target_id}",
        "source_id": source_id,
        "target_id": target_id,
        "relation_type": relation_type,
        "properties": {"description": desc}
    }

def get_node(node_id: str, db_path: str = DB_FILE) -> Optional[Dict[str, Any]]:
    """Retrieves a single node by its ID from Kuzu."""
    conn = get_connection(db_path)
    query = "MATCH (n:Node {id: $id}) RETURN n.id, n.type, n.name, n.description"
    result = conn.execute(query, {"id": node_id})
    if result.has_next():
        row = result.get_next()
        return {
            "id": row[0],
            "type": row[1],
            "name": row[2],
            "description": row[3],
            "properties": {} # For schema compatibility
        }
    return None

def get_all_nodes(db_path: str = DB_FILE) -> List[Dict[str, Any]]:
    """Retrieves all Node records from Kuzu Node Table."""
    conn = get_connection(db_path)
    query = "MATCH (n:Node) RETURN n.id, n.type, n.name, n.description"
    result = conn.execute(query)
    nodes = []
    while result.has_next():
        row = result.get_next()
        nodes.append({
            "id": row[0],
            "type": row[1],
            "name": row[2],
            "description": row[3],
            "properties": {}
        })
    return nodes

def get_all_edges(db_path: str = DB_FILE) -> List[Dict[str, Any]]:
    """Retrieves all relationship edges across all Kuzu relationship tables."""
    conn = get_connection(db_path)
    edges = []
    relationship_types = ["HAS_SKILL", "HAS_TOOL", "REQUIRES_TOOL", "BASED_ON", "REFERENCES", "MENTIONS", "IS_A"]
    for rel in relationship_types:
        query = f"MATCH (a:Node)-[r:{rel}]->(b:Node) RETURN a.id, b.id, r.description"
        result = conn.execute(query)
        while result.has_next():
            row = result.get_next()
            edges.append({
                "id": f"{row[0]}_{rel}_{row[1]}",
                "source_id": row[0],
                "target_id": row[1],
                "relation_type": rel,
                "properties": {"description": row[2] or ""}
            })
    return edges

def get_subgraph(start_node_ids: List[str], max_depth: int = 2, db_path: str = DB_FILE) -> Dict[str, Any]:
    """
    Traverses the Kuzu property graph starting from specific node IDs up to a given depth.
    Uses BFS expansion in Python querying the property edges to assemble nodes and relationships.
    """
    if not start_node_ids:
        return {"nodes": [], "edges": []}

    visited_nodes = set()
    collected_edges = []
    frontier = set(start_node_ids)
    
    conn = get_connection(db_path)
    relationship_types = ["HAS_SKILL", "HAS_TOOL", "REQUIRES_TOOL", "BASED_ON", "REFERENCES", "MENTIONS", "IS_A"]
    
    for depth in range(max_depth + 1):
        if not frontier:
            break
            
        visited_nodes.update(frontier)
        if depth == max_depth:
            break
            
        next_frontier = set()
        for node_id in frontier:
            for rel in relationship_types:
                # Query edges connected to this node
                query = f"""
                MATCH (a:Node)-[r:{rel}]->(b:Node)
                WHERE a.id = $id OR b.id = $id
                RETURN a.id, b.id, r.description
                """
                result = conn.execute(query, {"id": node_id})
                
                while result.has_next():
                    row = result.get_next()
                    edge = {
                        "id": f"{row[0]}_{rel}_{row[1]}",
                        "source_id": row[0],
                        "target_id": row[1],
                        "relation_type": rel,
                        "properties": {"description": row[2] or ""}
                    }
                    
                    # Avoid duplicate edges
                    if edge not in collected_edges:
                        collected_edges.append(edge)
                        
                    # Track nodes to visit next
                    src, tgt = row[0], row[1]
                    if src not in visited_nodes:
                        next_frontier.add(src)
                    if tgt not in visited_nodes:
                        next_frontier.add(tgt)
                        
        frontier = next_frontier

    # Retrieve all collected nodes
    nodes = []
    if visited_nodes:
        # Since Cypher IN checks are easy, let's query all nodes invisited_nodes
        for nid in visited_nodes:
            node_data = get_node(nid, db_path=db_path)
            if node_data:
                nodes.append(node_data)
                
    return {"nodes": nodes, "edges": collected_edges}
