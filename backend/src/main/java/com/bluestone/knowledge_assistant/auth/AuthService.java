package com.bluestone.knowledge_assistant.auth;

import com.bluestone.knowledge_assistant.auth.dto.AuthResponse;
import com.bluestone.knowledge_assistant.auth.dto.LoginRequest;
import com.bluestone.knowledge_assistant.auth.dto.RegisterRequest;
import com.bluestone.knowledge_assistant.auth.dto.UserDto;
import com.bluestone.knowledge_assistant.common.EmailAlreadyRegisteredException;
import com.bluestone.knowledge_assistant.common.UnauthorizedException;
import com.bluestone.knowledge_assistant.security.jwt.JwtService;
import com.bluestone.knowledge_assistant.security.userdetails.UserPrincipal;
import com.bluestone.knowledge_assistant.user.Role;
import com.bluestone.knowledge_assistant.user.RoleName;
import com.bluestone.knowledge_assistant.user.RoleRepository;
import com.bluestone.knowledge_assistant.user.User;
import com.bluestone.knowledge_assistant.user.UserRepository;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.util.List;
import java.util.UUID;

@Service
@Transactional(readOnly = true)
public class AuthService {

    private final AuthenticationManager authenticationManager;
    private final UserRepository userRepository;
    private final RoleRepository roleRepository;
    private final PasswordEncoder passwordEncoder;
    private final JwtService jwtService;
    private final RefreshTokenService refreshTokenService;

    public AuthService(AuthenticationManager authenticationManager,
                       UserRepository userRepository,
                       RoleRepository roleRepository,
                       PasswordEncoder passwordEncoder,
                       JwtService jwtService,
                       RefreshTokenService refreshTokenService) {
        this.authenticationManager = authenticationManager;
        this.userRepository = userRepository;
        this.roleRepository = roleRepository;
        this.passwordEncoder = passwordEncoder;
        this.jwtService = jwtService;
        this.refreshTokenService = refreshTokenService;
    }

    /**
     * Creates an account and returns its public profile.
     *
     * <p>Deliberately does NOT return tokens. Sign-up and sign-in stay separate so that
     * there is exactly one place where credentials are exchanged for a session, and so
     * a new user immediately proves the password they just chose actually works.
     *
     * <p>New accounts get ROLE_USER only. Nothing self-service may grant ROLE_ADMIN.
     */
    @Transactional
    public UserDto register(RegisterRequest request) {
        String email = request.email().trim().toLowerCase();

        // Checked first for a clean 409, but the unique constraint on users.email is
        // what actually guarantees it — two simultaneous sign-ups would both pass this
        // check and the database has to be the arbiter.
        if (userRepository.findByEmail(email).isPresent()) {
            throw new EmailAlreadyRegisteredException("An account with this email already exists.");
        }

        User user = new User(
                email,
                passwordEncoder.encode(request.password()),
                request.name().trim(),
                Instant.now());

        Role userRole = roleRepository.findByName(RoleName.ROLE_USER)
                .orElseThrow(() -> new IllegalStateException("ROLE_USER is missing; V10 seeds it"));
        user.addRole(userRole);

        try {
            userRepository.saveAndFlush(user);
        } catch (org.springframework.dao.DataIntegrityViolationException e) {
            // Lost the race described above.
            throw new EmailAlreadyRegisteredException("An account with this email already exists.");
        }

        return new UserDto(user.getId(), user.getEmail(), user.getName());
    }

    /**
     * Authenticates credentials and returns a fresh token pair.
     *
     * <p>Password checking is delegated to the {@code AuthenticationManager} rather than
     * comparing hashes here: that is what routes it through {@code DaoAuthenticationProvider},
     * which also performs a dummy hash on unknown accounts so a wrong email and a wrong
     * password take the same amount of time.
     */
    @Transactional
    public AuthResponse login(LoginRequest request) {
        UserPrincipal principal;
        try {
            var authentication = authenticationManager.authenticate(
                    new UsernamePasswordAuthenticationToken(request.email(), request.password()));
            principal = (UserPrincipal) authentication.getPrincipal();
        } catch (AuthenticationException e) {
            // One message for every failure mode — no account enumeration.
            throw new UnauthorizedException("Invalid email or password");
        }

        User user = userRepository.findWithRolesById(principal.getId())
                .orElseThrow(() -> new UnauthorizedException("Invalid email or password"));

        return buildResponse(principal, user);
    }

    /**
     * Exchanges a refresh token for a new pair, rotating the refresh token in the process.
     */
    @Transactional
    public AuthResponse refresh(String refreshToken) {
        User user = refreshTokenService.consume(refreshToken);

        // Re-read through the roles graph: consume() returns a lazily-associated user, and
        // the principal needs its authorities resolved.
        User withRoles = userRepository.findWithRolesById(user.getId())
                .orElseThrow(() -> new UnauthorizedException("Invalid refresh token"));

        return buildResponse(UserPrincipal.from(withRoles), withRoles);
    }

    /** Invalidates a single refresh token. The access token remains valid until it expires. */
    @Transactional
    public void logout(String refreshToken) {
        refreshTokenService.revoke(refreshToken);
    }

    /** Invalidates every refresh token the user holds. */
    @Transactional
    public void logoutEverywhere(UUID userId) {
        refreshTokenService.revokeAllForUser(userId);
    }

    private AuthResponse buildResponse(UserPrincipal principal, User user) {
        String accessToken = jwtService.generateAccessToken(principal);
        String refreshToken = refreshTokenService.issue(user);

        List<String> roles = principal.getAuthorities().stream()
                .map(GrantedAuthority::getAuthority)
                .toList();

        return AuthResponse.of(
                accessToken,
                refreshToken,
                jwtService.accessTokenTtl().toSeconds(),
                new UserDto(user.getId(), user.getEmail(), user.getName()),
                roles);
    }
}
