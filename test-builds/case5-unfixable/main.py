"""
CASE 5 Test: Unfixable error (requires external dependency not in repo)

This simulates an error that can't be fixed automatically because it
requires installing a system package or external dependency.
"""
import some_nonexistent_package_that_doesnt_exist

def main():
    some_nonexistent_package_that_doesnt_exist.do_something()
    print("This will never work")

if __name__ == "__main__":
    main()
