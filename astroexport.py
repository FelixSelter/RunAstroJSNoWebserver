import json
from pathlib import Path
from random import randint
from typing import Dict, List, Set
from typing_extensions import Self
import re

module_loader_name = "MyModuleLoader"


class JSModule:
    import_regex = r'import\{(\w+(?: as \w+)?(?:,\w+(?: as \w+)?)*)\}from"(.+?)"'
    simple_import_regex = r'import"(.+?)"'
    export_regex = r'export\{(.+(?: as \w+)?(?:,\w+(?: as \w+)?)*)\}'

    loaded_modules: Dict[Path, Self] = {}

    @staticmethod
    def load(src: Path):
        if src.resolve() in JSModule.loaded_modules:
            return JSModule.loaded_modules[src.resolve()]
        return JSModule(src)

    def __init__(self, src: Path):
        assert src not in JSModule.loaded_modules
        self.file_name = src.stem

        # Assign unique id and make module publicly available
        self.id = None
        other_ids = list(map(lambda x: x.id, JSModule.loaded_modules.values()))
        while self.id is None or self.id in other_ids:
            self.id = randint(0, 10000000)
        JSModule.loaded_modules[src.resolve()] = self

        src_code = src.read_text(encoding="utf-8")

        print(f"\t- Processing script {self.id}: {src}")
        self.dependencies: List[Self] = []

        # Find all exports
        for export_match in re.finditer(self.export_regex, src_code):
            exports = list(map(lambda x: x.split(" as "),
                           export_match.group(1).split(",")))
            print(f"\t\t- Found exports: {exports}")
            new_export = f"window.{module_loader_name}['{self.id}'] = {{"+",".join(
                i[0] if len(i) == 0 else f'{i[1]}:{i[0]}' for i in exports)+f"}}"
            src_code = src_code.replace(export_match.group(0), new_export)

        # Find all normal imports
        for import_match in re.finditer(self.import_regex, src_code):
            imports = list(map(lambda x: x.split(" as "),
                           import_match.group(1).split(",")))
            import_src = import_match.group(2)
            print(f"\t\t- Found imports from {import_src}: {imports}")
            m = JSModule.load(src.parent / import_src)
            self.dependencies.append(m)
            new_import = "const {"+",".join(i[0] if len(i) == 1 else f'{i[0]}:{i[1]}' for i in imports)+f"}} = window.{module_loader_name}['{m.id}']"
            src_code = src_code.replace(import_match.group(0), new_import)

        # Find polyfill imports that only execute top level code
        for import_match in re.finditer(self.simple_import_regex, src_code):
            import_src = import_match.group(1)
            print(f"\t\t- Polyfill import {import_src}")
            m = JSModule.load(src.parent / import_src)
            self.dependencies.append(m)
            src_code = src_code.replace(import_match.group(0), "")

        awaited_imports = [
            f"!window.{module_loader_name}[\"{dep.id}\"]" for dep in self.dependencies]
        await_statement = f'while ({" || ".join(awaited_imports)}) {{console.log("{module_loader_name} module {self.id} waiting for {", ".join([str(dep.id) for dep in self.dependencies])}");await new Promise(r => setTimeout(r, 50)); console.log("{module_loader_name} loaded module {self.id}")}}' if not len(
            self.dependencies) == 0 else ""
        
        
        self.module_code = f'<script type="module">if(window.{module_loader_name}===undefined)window.{module_loader_name}={{}};' + \
            await_statement+src_code+"</script>"


class HTMLPage:
    component_url_regex = r'component-url="(.+?)"'
    renderer_url_regex = r'renderer-url="(.+?)"'
    body_regex = r'<body.*?>'
    render_search_text = """let n=this.getAttribute("renderer-url"),[h,{default:p}]=await Promise.all([import(this.getAttribute("component-url")),n?import(n):()=>()=>{}]),u=this.getAttribute("component-export")||"default";if(!u.includes("."))this.Component=h[u];else{this.Component=h;for(let f of u.split("."))this.Component=this.Component[f]}return this.hydrator=p,this.hydrate"""

    def __init__(self, src: Path):
        print(f"\nProcessing page: {src}")
        src_code = src.read_text(encoding="utf-8")

        # Extract all renderers and components that need to be loaded
        scripts: Set[JSModule] = set()
        for (script_type, script_regex) in [("renderer", self.renderer_url_regex), ("component", self.component_url_regex)]:
            for script_match in re.finditer(script_regex, src_code):
                script_src = script_match.group(1)
                print(f"\t- Found {script_type}: {script_src}")
                scripts.add(JSModule.load(src.parent / script_src))

        # Also load all dependencies
        for script in list(scripts):
            for dependency in script.dependencies:
                scripts.add(dependency)

        # Extract the renderer
        render_replacement_text = (
            f'if(window.{module_loader_name}===undefined)window.{module_loader_name}={{}};\n'
            f"const urls = {json.dumps(dict(map(lambda s: (s.file_name, str(s.id)), scripts)))};\n"
            f'for (const module_id of Object.values(urls)) {{\n'
            f'while (!window.MyModuleLoader[module_id]) {{\n'
            f'console.log("{module_loader_name} renderer waiting for",module_id);\n'
            'await new Promise(r => setTimeout(r, 50));\n'
            '}\n'
            '}'
            f'console.log("{module_loader_name} Executing renderer");\n'
            f'const renderer_url = urls[this.getAttribute("renderer-url").split("/").at(-1).replace(".js","")];\n'
            f'const component_url = urls[this.getAttribute("component-url").split("/").at(-1).replace(".js","")];\n'
            f"this.hydrator = window.{module_loader_name}[renderer_url].default;\n"
            f'this.Component = window.{module_loader_name}[component_url][this.getAttribute("component-export")];\n'
            "return this.hydrator, this.hydrate;"
        )

        if not self.render_search_text in src_code:
            print(f"{src} has no astro renderer attached")
        src_code = src_code.replace(
            self.render_search_text, render_replacement_text)

        # Add all script imports
        body_match = re.search(self.body_regex, src_code)
        if body_match is None:
            print("\n"+"-"*30+"\n",
                  f"Skipping {src} because it has no body tag\n", "-"*30+"\n")
            return
        src_code = src_code.replace(body_match.group(0), body_match.group(
            0) + "".join(map(lambda s: s.module_code, scripts)))

        # Export the file
        src.write_text(src_code, encoding="utf-8")


# Transform all HTML pages
if __name__ == "__main__":
    distribution_dir = Path("./dist")
    for html_file in distribution_dir.rglob("*.html"):
        page = HTMLPage(html_file)
