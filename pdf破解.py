import itertools
import PyPDF2

def brute_force_pdf_password(pdf_path, max_length=4):
    """
    Tries to brute-force the password of a PDF by generating all possible combinations
    of lowercase letters and numbers up to a given length.

    :param pdf_path: Path to the password-protected PDF file.
    :param max_length: Maximum length of password to try.
    """
    chars = "abcdefghijklmnopqrstuvwxyz0123456789"
    try:
        with open(pdf_path, 'rb') as pdf_file:
            reader = PyPDF2.PdfReader(pdf_file)

            if not reader.is_encrypted:
                print("The PDF is not encrypted.")
                return

            print(f"Starting brute force attack (max length: {max_length})...")

            for length in range(1, max_length + 1):
                for password_tuple in itertools.product(chars, repeat=length):
                    password = ''.join(password_tuple)
                    try:
                        if reader.decrypt(password):
                            print(f"Password found: {password}")
                            return password
                    except Exception:
                        pass
            print("Password not found with brute force attack.")
    except FileNotFoundError:
        print(f"Error: The file {pdf_path} was not found.")
    except Exception as e:
        print(f"An error occurred: {e}")

# Example usage
pdf_path = 'D:\安全信封-合成工艺.pdf'
brute_force_pdf_password(pdf_path, max_length=8)
