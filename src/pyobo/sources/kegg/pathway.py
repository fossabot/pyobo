# -*- coding: utf-8 -*-

"""Convert KEGG Pathways to OBO.

Run with ``python -m pyobo.sources.kegg.pathway``
"""

import urllib.error
from collections import defaultdict
from typing import Iterable, List, Mapping, Tuple

import click
from more_click import verbose_option
from tqdm import tqdm

from pyobo.sources.kegg.api import (
    KEGG_PATHWAY_PREFIX, ensure_link_pathway_genome, ensure_list_pathway_genome, ensure_list_pathways,
)
from pyobo.sources.kegg.genome import KEGGGenome, iter_kegg_genomes
from pyobo.struct import Obo, Reference, Term, TypeDef, from_species, has_part

from_kegg_species = TypeDef(
    reference=Reference.default('inKeggTaxon', 'in KEGG taxon'),
)

species_specific = TypeDef(
    reference=Reference.default('speciesSpecific', 'Species Specific'),
    definition='X speciesSpecific Y means that Y is a general phenomena, '
               'like a pathway, and X is the version that appears in a species. X should state which'
               'species with RO:0002162 (in taxon)',
)


def get_obo() -> Obo:
    """Get KEGG Pathways as OBO."""
    return Obo(
        ontology=KEGG_PATHWAY_PREFIX,
        iter_terms=iter_terms,
        name='KEGG Pathways',
        typedefs=[from_kegg_species, from_species, species_specific, has_part],
        auto_generated_by=f'bio2obo:{KEGG_PATHWAY_PREFIX}',
    )


def iter_terms() -> Iterable[Term]:
    """Iterate over terms for KEGG Pathway."""
    yield from _iter_map_terms()
    for kegg_genome, list_pathway_path, link_pathway_path in iter_kegg_pathway_paths():
        yield from _iter_genome_terms(
            list_pathway_path=list_pathway_path,
            link_pathway_path=link_pathway_path,
            kegg_genome=kegg_genome,
        )


def _get_link_pathway_map(path: str) -> Mapping[str, List[str]]:
    rv = defaultdict(list)
    with open(path) as file:
        for line in file:
            protein, pathway = line.strip().split('\t')
            pathway = pathway[len('path:'):]
            rv[pathway].append(pathway)
    return {k: sorted(v) for k, v in rv.items()}


def _iter_map_terms() -> Iterable[Term]:
    for identifier, name in ensure_list_pathways().items():
        yield Term(
            reference=Reference(
                prefix=KEGG_PATHWAY_PREFIX,
                identifier=identifier,
                name=name,
            ),
        )


def _iter_genome_terms(
    *,
    list_pathway_path: str,
    link_pathway_path: str,
    kegg_genome: KEGGGenome,
) -> Iterable[Term]:
    terms = {}
    with open(list_pathway_path) as file:
        list_pathway_lines = [line.strip() for line in file]
    for line in list_pathway_lines:
        line = line.strip()
        pathway_id, name = [part.strip() for part in line.split('\t')]
        pathway_id = pathway_id[len('path:'):]

        _start = min(i for i, e in enumerate(pathway_id) if e.isnumeric())
        pathway_code = pathway_id[_start:]

        terms[pathway_id] = term = Term(
            reference=Reference(
                prefix=KEGG_PATHWAY_PREFIX,
                identifier=pathway_id,
                name=name,
            ),
        )
        term.append_relationship(
            species_specific,
            Reference(prefix=KEGG_PATHWAY_PREFIX, identifier=f'map{pathway_code}'),
        )
        term.append_relationship(
            from_kegg_species,
            kegg_genome.get_reference(),
        )
        if kegg_genome.taxonomy_id is not None:
            term.set_species(kegg_genome.taxonomy_id)

    for pathway_id, protein_ids in _get_link_pathway_map(link_pathway_path).items():
        term = terms.get(pathway_id)
        if term is None:
            tqdm.write(f'could not find kegg.pathway:{pathway_id}')
        for protein_id in protein_ids:
            term.append_relationship(has_part, Reference(
                prefix='kegg.genes',
                identifier=protein_id,
            ))

    yield from terms.values()


def iter_kegg_pathway_paths() -> Iterable[Tuple[KEGGGenome, str, str]]:
    """Get paths for the KEGG Pathway files."""
    for kegg_genome in iter_kegg_genomes():
        try:
            list_pathway_path = ensure_list_pathway_genome(kegg_genome.identifier)
            link_pathway_path = ensure_link_pathway_genome(kegg_genome.identifier)
        except urllib.error.HTTPError as e:
            code = e.getcode()
            if code != 404:
                msg = f'[HTTP {code}] Error downloading {kegg_genome.identifier} ({kegg_genome.name}'
                if kegg_genome.taxonomy_id is None:
                    msg = f'{msg}): {e.geturl()}'
                else:
                    msg = f'{msg}; taxonomy:{kegg_genome.taxonomy_id}): {e.geturl()}'
                tqdm.write(msg)
        else:
            yield kegg_genome, list_pathway_path, link_pathway_path


@click.command()
@verbose_option
def _main():
    get_obo().write_default()


if __name__ == '__main__':
    _main()
