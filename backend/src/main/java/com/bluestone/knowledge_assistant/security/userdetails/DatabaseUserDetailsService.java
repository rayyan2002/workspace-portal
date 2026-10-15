package com.bluestone.knowledge_assistant.security.userdetails;

import com.bluestone.knowledge_assistant.user.UserRepository;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * Loads users for the {@code DaoAuthenticationProvider} during password login.
 *
 * <p>The JWT filter does NOT go through here — it builds the principal from the token's
 * own claims, which is the entire point of a stateless access token.
 */
@Service
public class DatabaseUserDetailsService implements UserDetailsService {

    private final UserRepository userRepository;

    public DatabaseUserDetailsService(UserRepository userRepository) {
        this.userRepository = userRepository;
    }

    @Override
    @Transactional(readOnly = true)
    public UserDetails loadUserByUsername(String email) throws UsernameNotFoundException {
        return userRepository.findByEmail(email)
                .map(UserPrincipal::from)
                // Message is generic on purpose; Spring Security maps this to
                // BadCredentialsException so login cannot be used to enumerate accounts.
                .orElseThrow(() -> new UsernameNotFoundException("Invalid email or password"));
    }
}
