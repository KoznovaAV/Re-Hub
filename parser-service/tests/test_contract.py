import copy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from jsonschema.exceptions import ValidationError
from app.contract import validate_result
from app.generate_test_data import generate
from app.customer_clients import parse_file as clients
from app.customer_xlsx import parse_file as snapshot

class ContractTest(unittest.TestCase):
    def test_both_parsers_and_nested_mutations(self):
        with TemporaryDirectory() as tmp:
            p=Path(tmp);generate(p,30,42)
            for name,parse in [("clients",clients),("snapshot_1",snapshot),("snapshot_2",snapshot)]:
                result=parse(p/(name+".xlsx"),json.loads((p/(name+".context.json")).read_text()))
                validate_result(result)
                mutations=[]
                for target in [(),("rows",0),("rows",0,"source"),("rows",0,"data")]:
                    bad=copy.deepcopy(result);obj=bad
                    for key in target:obj=obj[key]
                    obj["unexpected"]=True;mutations.append(bad)
                bad=copy.deepcopy(result);del bad["rows"][0]["data"]["external_id"];mutations.append(bad)
                bad=copy.deepcopy(result);bad["rows"][0]["data"]["external_id"]="bad";mutations.append(bad)
                bad=copy.deepcopy(result);bad["rows"][0]["source"]["row"]=0;mutations.append(bad)
                if name!="clients":
                    bad=copy.deepcopy(result);bad["rows"][0]["data"]["unsent_docs"]=-1;mutations.append(bad)
                for bad in mutations:
                    with self.subTest(name=name,bad=bad):
                        with self.assertRaises(ValidationError):validate_result(bad)

    def test_examples_match_contract(self):
        root=Path(__file__).resolve().parents[2]/"contracts/examples"
        for file in root.glob("parser-result*.json"):
            with self.subTest(file=file.name):validate_result(json.loads(file.read_text()))
