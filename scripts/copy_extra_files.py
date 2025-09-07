"""
MkDocs hook to copy extra files to site root after build.
This ensures llms.txt is available at the root URL.
"""

import os
import shutil
from mkdocs.config import Config


def on_post_build(config: Config, **kwargs) -> None:
    """
    Copy extra files to site directory after build.
    """
    site_dir = config['site_dir']
    
    # Copy llms.txt to site root
    src_path = 'llms.txt'
    dst_path = os.path.join(site_dir, 'llms.txt')
    
    if os.path.exists(src_path):
        shutil.copy2(src_path, dst_path)
        print(f"✅ Copied {src_path} to site root")
    else:
        print(f"❌ Warning: {src_path} not found")