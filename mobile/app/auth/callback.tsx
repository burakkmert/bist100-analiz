// E-posta doğrulama / OAuth dönüş bağlantısı uygulamayı buraya açar.
// Oturum işlemi auth store'da yapılır; burası yalnızca kullanıcıyı ana akışa geri yollar.
import { Redirect } from 'expo-router';

export default function AuthCallback() {
  return <Redirect href="/" />;
}
