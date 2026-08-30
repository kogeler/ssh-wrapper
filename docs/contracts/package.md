# Package And Distribution Contract

## Assertions

### `PKG-001` - One human-maintained version source

**Contract:** Root `.version` MUST contain one stable `X.Y.Z` value and MUST be
the only human-maintained version. PEP 621 metadata MUST read it dynamically,
`ssh_wrapper.__version__` MUST resolve it in source and installed contexts, and
the changelog MUST contain one matching dated section.

**Evidence:**

- [`test_version_metadata_is_synchronized`](../../tests/test_project_boundary.py) - `tests/test_project_boundary.py::test_version_metadata_is_synchronized`
- [`test_version_resolution_uses_installed_metadata_and_safe_fallback`](../../tests/test_public_api.py) - `tests/test_public_api.py::test_version_resolution_uses_installed_metadata_and_safe_fallback`
- [`test_version_rejects_metadata_drift_and_non_increment`](../../tests/test_release_governance.py) - `tests/test_release_governance.py::test_version_rejects_metadata_drift_and_non_increment`

### `PKG-002` - PyPI metadata and README are portable

**Contract:** Distribution metadata MUST use the `ssh-wrapper` name, identify
`kogeler` as author and maintainer, declare only CPython 3.13 and 3.14 on Linux,
include the complete reviewed classifiers, keywords, license, maintainer
extras, and public project URLs, and render a README whose links remain valid
on PyPI.

**Evidence:**

- [`test_pypi_metadata_exposes_exact_public_routes_and_python`](../../tests/test_package_metadata.py) - `tests/test_package_metadata.py::test_pypi_metadata_exposes_exact_public_routes_and_python`
- [`test_pypi_readme_uses_only_portable_https_links`](../../tests/test_package_metadata.py) - `tests/test_package_metadata.py::test_pypi_readme_uses_only_portable_https_links`
- [`test_public_install_examples_use_the_current_exact_version`](../../tests/test_package_metadata.py) - `tests/test_package_metadata.py::test_public_install_examples_use_the_current_exact_version`

### `PKG-003` - Release builds contain one normalized pair

**Contract:** A package build MUST run without network access after the locked
packaging environment exists, MUST produce exactly one `py3-none-any` wheel and
one normalized sdist, and MUST make equivalent clean trees byte-identical.
These are Python distribution archives, not standalone applications; the build
MUST NOT produce native executables or platform-specific application bundles.

**Evidence:**

- [`test_normalization_makes_equivalent_archives_byte_identical`](../../tests/test_distribution_tools.py) - `tests/test_distribution_tools.py::test_normalization_makes_equivalent_archives_byte_identical`
- [`test_package_make_contract_builds_smokes_and_reuses_exact_pair`](../../tests/test_package_metadata.py) - `tests/test_package_metadata.py::test_package_make_contract_builds_smokes_and_reuses_exact_pair`

### `PKG-004` - Archive inventories are exact and typed

**Contract:** The wheel and sdist MUST contain only the reviewed package and
metadata inventories, MUST include `LICENSE`, README metadata, and `py.typed`,
MUST use canonical modes and timestamps, and MUST exclude tests, caches,
private paths, foreign products, and generated repository state. Wheel RECORD
hashes and sizes MUST match every member.

**Evidence:**

- [`test_sdist_manifest_excludes_nonproduct_trees`](../../tests/test_package_metadata.py) - `tests/test_package_metadata.py::test_sdist_manifest_excludes_nonproduct_trees`
- [`test_inline_typing_configuration_is_packaged`](../../tests/test_package_metadata.py) - `tests/test_package_metadata.py::test_inline_typing_configuration_is_packaged`

### `PKG-005` - Both artifacts pass clean installed-package smoke

**Contract:** CI MUST install the wheel and an offline wheel built from the
sdist into separate fresh environments outside the source tree, verify import
and distribution versions, exercise a harmless lifecycle, and prove strict
mypy visibility through the installed interpreter.

**Evidence:**

- [`test_package_make_contract_builds_smokes_and_reuses_exact_pair`](../../tests/test_package_metadata.py) - `tests/test_package_metadata.py::test_package_make_contract_builds_smokes_and_reuses_exact_pair`

### `PKG-006` - Checksums cover the immutable release pair

**Contract:** `SHA256SUMS.txt` MUST contain exactly one SHA-256 line for the
wheel and one for the sdist, MUST reject extra or missing files, and MUST be
reused with those same files by PyPI and GitHub publication.

**Evidence:**

- [`test_checksum_inventory_is_exact_and_self_verifying`](../../tests/test_distribution_tools.py) - `tests/test_distribution_tools.py::test_checksum_inventory_is_exact_and_self_verifying`
- [`test_release_reuses_ci_and_shared_python_distributions`](../../tests/test_ci_policy.py) - `tests/test_ci_policy.py::test_release_reuses_ci_and_shared_python_distributions`
