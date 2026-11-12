import unittest
from scripts.build_changes import compare

class ChangeDetectorTests(unittest.TestCase):
    def test_same_service_date_no_change(self):
        state={"2026-11-13":{"123":{"A|4|0":{"routes":{"r":[["123","A"]]},"departures":["08:00"]}}}}
        self.assertEqual(dict(compare(state,state,"2026-11-13")),{})
    def test_route_change(self):
        a={"2026-11-13":{"123":{"A|4|0":{"routes":{"r":[["123","A"]]},"departures":["08:00"]}}}}
        b={"2026-11-13":{"123":{"A|4|0":{"routes":{"s":[["123","A"],["124","B"]]},"departures":["08:00"]}}}}
        self.assertEqual(compare(a,b,"2026-11-13")["123"][0]["addedStops"],["124"])
    def test_new_line(self):
        a={"2026-11-13":{}}
        b={"2026-11-13":{"123":{"A|6|0":{"routes":{},"departures":[]}}}}
        self.assertEqual(compare(a,b,"2026-11-13")["123"][0]["type"],"added")
if __name__=="__main__":unittest.main()
