import unittest

from utils.alias import Alias


class AliasTests(unittest.TestCase):
    def setUp(self):
        self.aliases = Alias()

    def test_cctv_regional_variants_do_not_match_general_channels(self):
        self.assertEqual(
            self.aliases.get_primary("CCTV5＋体育赛事"),
            "CCTV-5+",
        )
        self.assertEqual(
            self.aliases.get_primary("CCTV4中文國際歐洲IPV6"),
            "CCTV-4欧洲",
        )
        self.assertEqual(
            self.aliases.get_primary("CCTV-1綜合"),
            "CCTV-1",
        )

    def test_distinct_channels_are_not_aliases(self):
        first_theatre_aliases = self.aliases.get("第一剧场")
        military_documentary_aliases = self.aliases.get("NewTV军事纪实")

        self.assertNotIn("风云剧场", first_theatre_aliases)
        self.assertNotIn("中国电影", first_theatre_aliases)
        self.assertNotIn("魅力潇湘", military_documentary_aliases)


if __name__ == "__main__":
    unittest.main()
