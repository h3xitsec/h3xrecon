import sqlite3
import json
import os
from typing import AsyncGenerator, Dict, Any
from plugins.base import ReconPlugin
from loguru import logger
import asyncio

class FindSubdomainsCTFR(ReconPlugin):
    @property
    def name(self) -> str:
        return os.path.splitext(os.path.basename(__file__))[0]

    def fetch_assets(self, conn):
        """Fetch all rows from the assets table."""
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM assets")
        columns = [description[0] for description in cursor.description]
        rows = cursor.fetchall()
        assets = {row[0]: dict(zip(columns, row)) for row in rows}  # Use the 'id' column as the key
        return assets

    def fetch_relations(self, conn):
        """Fetch all rows from the relations table."""
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM relations")
        columns = [description[0] for description in cursor.description]
        rows = cursor.fetchall()
        relations = [dict(zip(columns, row)) for row in rows]
        return relations

    async def execute(self, target: str) -> AsyncGenerator[Dict[str, Any], None]:
        logger.info(f"Running {self.name} on {target}")
        command = f"""
            amass enum -d {target}
        """
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            shell=True
        )

        logger.debug("Before waiting")
        await process.wait()
        logger.debug("After waiting")
        
        conn = sqlite3.connect('/root/.config/amass/amass.sqlite')

        # Fetch data from assets and relations
        assets = self.fetch_assets(conn)
        relations = self.fetch_relations(conn)
        logger.debug(relations)
        logger.debug(assets)
        # Organize the data into the desired format
        domains = []
        for asset_id, asset in assets.items():
            logger.debug(asset)
            # Extract domain name from the content field
            content = json.loads(asset["content"]) if asset["content"] else {}
            domain_entry = {
                "domain": content.get("name", ""),
            }
            
            # Add relation types as separate fields in attributes
            for relation in relations:
                if relation["from_asset_id"] == asset_id:
                    relation_type = relation["type"]
                    to_asset_id = relation["to_asset_id"]
                    related_asset = assets.get(to_asset_id, {})
                    related_name = json.loads(related_asset.get("content", "{}")).get("name", "")
                    
                    # Map relation types to appropriate attribute names
                    attribute_name = f"{relation_type}s"  # e.g., 'ns_record' -> 'ns_records'
                    domain_entry.setdefault(attribute_name, []).append(related_name)
            
            yield domain_entry


