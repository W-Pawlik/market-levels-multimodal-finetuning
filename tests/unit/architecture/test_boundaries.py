"""Protect dependency boundaries that make pure computations independently usable."""
import ast
import importlib.util
from pathlib import Path
import subprocess
import sys
import unittest

from support.paths import PROJECT


def dependency_graph():
    root = PROJECT / 'src'
    paths = {'.'.join(p.relative_to(root).with_suffix('').parts).removesuffix('.__init__'): p
             for p in (root / 'market_levels').rglob('*.py')}
    graph = {}
    for name, path in paths.items():
        package = name if path.name == '__init__.py' else name.rpartition('.')[0]
        deps = set()
        for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
            if isinstance(node, ast.ImportFrom):
                target = importlib.util.resolve_name('.' * node.level + (node.module or ''), package) if node.level else node.module
                for alias in node.names:
                    child = target + '.' + alias.name
                    if child in paths:
                        deps.add(child)
                    elif target in paths:
                        deps.add(target)
            elif isinstance(node, ast.Import):
                deps.update(a.name for a in node.names if a.name in paths)
        graph[name] = deps
    return graph


class DependencyBoundaryTests(unittest.TestCase):
    def test_core_shared_domain_and_cli_boundaries(self):
        for module, deps in dependency_graph().items():
            for dep in deps:
                with self.subTest(module=module, dependency=dep):
                    if module.startswith('market_levels.core.'):
                        self.assertTrue(dep.startswith('market_levels.core.'))
                    if module.startswith('market_levels.shared.'):
                        self.assertTrue(dep.startswith('market_levels.shared.'))
                    if '.domain.' in module:
                        self.assertFalse(any(part in dep for part in ('.workflows.', '.io.', '.cli.')))
                    if not module.startswith('market_levels.cli.'):
                        self.assertFalse(dep.startswith('market_levels.cli.'))

    def test_no_internal_import_cycles_including_local_imports(self):
        graph = dependency_graph()
        visited, active = set(), []
        def visit(node):
            self.assertNotIn(node, active, ' -> '.join(active + [node]))
            if node in visited:
                return
            active.append(node)
            for dep in graph.get(node, ()):
                visit(dep)
            active.pop()
            visited.add(node)
        for node in graph:
            visit(node)

    def test_pure_algorithms_import_without_matplotlib(self):
        code = (
            'import sys; '
            'import market_levels.core.numeric.atr; '
            'import market_levels.data_processing.synthetic.domain.generation.dispatch; '
            'import market_levels.charts.domain.metrics; '
            'import market_levels.labeling.domain.algorithm; '
            'import market_levels.evaluation.domain.scoring; '
            'assert not any(n == "matplotlib" or n.startswith("matplotlib.") for n in sys.modules)'
        )
        result = subprocess.run([sys.executable, '-I', '-X', 'utf8', '-c', code],
            capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(result.returncode, 0, result.stderr)
