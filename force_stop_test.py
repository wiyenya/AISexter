import os
import sys
import django

# Initialize Django settings so we can use settings and OctoClient
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'AIsexter.settings')
django.setup()

from parser.services import OctoClient  # noqa: E402


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("Usage: python force_stop_test.py <PROFILE_UUID> [<PROFILE_UUID> ...]")
        print("Environment: OCTO_API_TOKEN must be set")
        return 2

    octo = OctoClient.init_from_settings()
    uuids = argv[1:]

    any_failed = False
    for uuid in uuids:
        print(f"\n🛑 Force stopping via cloud API: {uuid}")
        try:
            success = octo.force_stop_profile(uuid)
            print("✅ Success" if success else "❌ Failed")
            if not success:
                any_failed = True
        except Exception as e:
            print(f"❌ Error: {e}")
            any_failed = True

    return 1 if any_failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))


