from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import pycountry


class CapabilityTier(str, Enum):
    STRONG = "strong"
    SUPPORTED = "supported"
    EXPERIMENTAL = "experimental"


@dataclass(frozen=True)
class Language:
    code: str
    english_name: str
    native_name: str
    script: str
    direction: str
    tier: CapabilityTier = CapabilityTier.SUPPORTED

    @property
    def display_name(self) -> str:
        return self.english_name if self.native_name == self.english_name else f"{self.english_name} — {self.native_name}"


class LanguageRegistry:
    def __init__(self, languages: list[Language]):
        self._languages = {item.code: item for item in languages}
        if len(self._languages) != len(languages):
            raise ValueError("Language codes must be unique")

    def get(self, code: str) -> Language:
        try:
            return self._languages[code]
        except KeyError as exc:
            raise KeyError(f"Unknown language capability: {code}") from exc

    def search(self, query: str) -> list[Language]:
        value = query.casefold().strip()
        return sorted(
            [item for item in self._languages.values() if value in " ".join((item.code, item.english_name, item.native_name, item.script)).casefold()],
            key=lambda item: (item.english_name.casefold(), item.script),
        )

    def for_model(self, model) -> list[Language]:
        return sorted((self.get(code) for code in model.languages if code != "*"), key=lambda item: item.english_name.casefold())


WHISPER_LANGUAGES = {
    "en":"English","zh":"Chinese","de":"German","es":"Spanish","ru":"Russian","ko":"Korean","fr":"French","ja":"Japanese","pt":"Portuguese","tr":"Turkish","pl":"Polish","ca":"Catalan","nl":"Dutch","ar":"Arabic","sv":"Swedish","it":"Italian","id":"Indonesian","hi":"Hindi","fi":"Finnish","vi":"Vietnamese","he":"Hebrew","uk":"Ukrainian","el":"Greek","ms":"Malay","cs":"Czech","ro":"Romanian","da":"Danish","hu":"Hungarian","ta":"Tamil","no":"Norwegian","th":"Thai","ur":"Urdu","hr":"Croatian","bg":"Bulgarian","lt":"Lithuanian","la":"Latin","mi":"Maori","ml":"Malayalam","cy":"Welsh","sk":"Slovak","te":"Telugu","fa":"Persian","lv":"Latvian","bn":"Bengali","sr":"Serbian","az":"Azerbaijani","sl":"Slovenian","kn":"Kannada","et":"Estonian","mk":"Macedonian","br":"Breton","eu":"Basque","is":"Icelandic","hy":"Armenian","ne":"Nepali","mn":"Mongolian","bs":"Bosnian","kk":"Kazakh","sq":"Albanian","sw":"Swahili","gl":"Galician","mr":"Marathi","pa":"Punjabi","si":"Sinhala","km":"Khmer","sn":"Shona","yo":"Yoruba","so":"Somali","af":"Afrikaans","oc":"Occitan","ka":"Georgian","be":"Belarusian","tg":"Tajik","sd":"Sindhi","gu":"Gujarati","am":"Amharic","yi":"Yiddish","lo":"Lao","uz":"Uzbek","fo":"Faroese","ht":"Haitian Creole","ps":"Pashto","tk":"Turkmen","nn":"Nynorsk","mt":"Maltese","sa":"Sanskrit","lb":"Luxembourgish","my":"Myanmar","bo":"Tibetan","tl":"Tagalog","mg":"Malagasy","as":"Assamese","tt":"Tatar","haw":"Hawaiian","ln":"Lingala","ha":"Hausa","ba":"Bashkir","jw":"Javanese","su":"Sundanese","yue":"Cantonese"
}

NLLB_CODES = """ace_Arab ace_Latn acm_Arab acq_Arab aeb_Arab afr_Latn ajp_Arab aka_Latn amh_Ethi apc_Arab arb_Arab ars_Arab ary_Arab arz_Arab asm_Beng ast_Latn awa_Deva ayr_Latn azb_Arab azj_Latn bak_Cyrl bam_Latn ban_Latn bel_Cyrl bem_Latn ben_Beng bho_Deva bjn_Arab bjn_Latn bod_Tibt bos_Latn bug_Latn bul_Cyrl cat_Latn ceb_Latn ces_Latn cjk_Latn ckb_Arab crh_Latn cym_Latn dan_Latn deu_Latn dik_Latn dyu_Latn dzo_Tibt ell_Grek eng_Latn epo_Latn est_Latn eus_Latn ewe_Latn fao_Latn pes_Arab fij_Latn fin_Latn fon_Latn fra_Latn fur_Latn fuv_Latn gla_Latn gle_Latn glg_Latn grn_Latn guj_Gujr hat_Latn hau_Latn heb_Hebr hin_Deva hne_Deva hrv_Latn hun_Latn hye_Armn ibo_Latn ilo_Latn ind_Latn isl_Latn ita_Latn jav_Latn jpn_Jpan kab_Latn kac_Latn kam_Latn kan_Knda kas_Arab kas_Deva kat_Geor knc_Arab knc_Latn kaz_Cyrl kbp_Latn kea_Latn khm_Khmr kik_Latn kin_Latn kir_Cyrl kmb_Latn kon_Latn kor_Hang kmr_Latn lao_Laoo lvs_Latn lij_Latn lim_Latn lin_Latn lit_Latn lmo_Latn ltg_Latn ltz_Latn lua_Latn lug_Latn luo_Latn lus_Latn mag_Deva mai_Deva mal_Mlym mar_Deva min_Latn mkd_Cyrl plt_Latn mlt_Latn mni_Beng khk_Cyrl mos_Latn mri_Latn zsm_Latn mya_Mymr nld_Latn nno_Latn nob_Latn npi_Deva nso_Latn nus_Latn nya_Latn oci_Latn gaz_Latn ory_Orya pag_Latn pan_Guru pap_Latn pol_Latn por_Latn prs_Arab pbt_Arab quy_Latn ron_Latn run_Latn rus_Cyrl sag_Latn san_Deva sat_Beng scn_Latn shn_Mymr sin_Sinh slk_Latn slv_Latn smo_Latn sna_Latn snd_Arab som_Latn sot_Latn spa_Latn als_Latn srd_Latn srp_Cyrl ssw_Latn sun_Latn swe_Latn swh_Latn szl_Latn tam_Taml tat_Cyrl tel_Telu tgk_Cyrl tgl_Latn tha_Thai tir_Ethi taq_Latn taq_Tfng tpi_Latn tsn_Latn tso_Latn tuk_Latn tum_Latn tur_Latn twi_Latn tzm_Tfng uig_Arab ukr_Cyrl umb_Latn urd_Arab uzn_Latn vec_Latn vie_Latn war_Latn wol_Latn xho_Latn ydd_Hebr yor_Latn yue_Hant zho_Hans zho_Hant zul_Latn""".split()

RTL_SCRIPTS = {"Arab", "Hebr"}
SCRIPT_NAMES = {"Arab":"Arabic","Latn":"Latin","Beng":"Bengali","Cyrl":"Cyrillic","Deva":"Devanagari","Ethi":"Ethiopic","Grek":"Greek","Gujr":"Gujarati","Hebr":"Hebrew","Jpan":"Japanese","Knda":"Kannada","Khmr":"Khmer","Mlym":"Malayalam","Mymr":"Myanmar","Orya":"Odia","Sinh":"Sinhala","Taml":"Tamil","Telu":"Telugu","Tfng":"Tifinagh","Thai":"Thai","Tibt":"Tibetan","Hang":"Hangul","Hans":"Simplified Han","Hant":"Traditional Han","Armn":"Armenian","Geor":"Georgian","Guru":"Gurmukhi","Laoo":"Lao"}


def _name(alpha3: str) -> str:
    language = pycountry.languages.get(alpha_3=alpha3)
    return language.name if language else alpha3.upper()


def default_registry() -> LanguageRegistry:
    records: dict[str, Language] = {}
    for code, name in WHISPER_LANGUAGES.items():
        records[code] = Language(code, name, name, "Auto", "rtl" if code in {"ar","he","fa","ur","yi","ps","sd"} else "ltr", CapabilityTier.STRONG if code in {"en","es","fr","de","pt","ja","zh"} else CapabilityTier.SUPPORTED)
    for code in NLLB_CODES:
        alpha3, script = code.split("_", 1)
        name = _name(alpha3)
        if code == "arb_Arab": name = "Arabic"
        records[code] = Language(code, name, name, SCRIPT_NAMES.get(script, script), "rtl" if script in RTL_SCRIPTS else "ltr")
    return LanguageRegistry(list(records.values()))

